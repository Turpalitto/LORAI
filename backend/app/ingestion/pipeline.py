"""Полный пайплайн: Load→Structure→Tables→ICD10→LLM→Validate→Chunk→Index."""
import re, uuid
from .pdf_loader import load_pages
from .table_parser import parse_tables
from .icd10_extractor import extract_icd10

HEADINGS = {
    "definition": [r"определение", r"что такое"],
    "diagnostics": [r"диагностик", r"обследован", r"жалобы", r"анамнез"],
    "treatment": [r"лечени", r"терапи"],
    "referral_criteria": [r"показания к госпитализации", r"госпитализац", r"направлен", r"показания к операц"],
    "prevention": [r"профилактик"],
    "complications": [r"осложнен"],
}
def detect_sections(pages: list[dict]) -> dict:
    full = "\n".join(p["text"] for p in pages)
    secs, cur, cur_page = {"raw": full}, None, 1
    # упрощённо: ищем заголовки, режем текст
    lines = full.split("\n")
    buf = {k: [] for k in HEADINGS}
    for ln in lines:
        low = ln.strip().lower()
        hit = None
        for sec, pats in HEADINGS.items():
            if any(re.search(p, low) for p in pats) and len(low) < 80:
                hit = sec; break
        if hit: cur = hit
        elif cur: buf[cur].append(ln)
    for k, v in buf.items(): secs[k] = "\n".join(v)[:6000]
    # сколько осмысленных секций реально нашлось (сырой текст не в счёт)
    found = [k for k in HEADINGS if secs.get(k, "").strip()]
    secs["sections_found"] = found
    # source_pages: эвристика — ищем на каких страницах встретились ключи
    sp = {}
    for sec, pats in HEADINGS.items():
        pg = [p["page"] for p in pages if any(re.search(pt, p["text"].lower()) for pt in pats)]
        if pg: sp[sec] = pg[:5]
    secs["source_pages"] = sp
    return secs

def chunk_text(text: str, meta: dict, size: int = 1500, overlap: int = 150) -> list[dict]:
    chunks, i = [], 0
    text = text or ""
    while i < len(text):
        chunks.append({**meta, "text": text[i:i+size]})
        i += size - overlap
    return chunks or [{**meta, "text": ""}]


# Строгие заголовки разделов КР: строка целиком равна названию главы
# (с необязательной нумерацией и двоеточием). Прежнее правило «строка < 80
# символов содержит ключевое слово» давало дребезг: 80 переключений раздела на
# 168 чанков, метки не соответствовали содержимому (см. scripts/check_section_labels.py).
_HEADING_RX = [
    ("definition", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:определение|этиология(?: и патогенез)?|"
                              r"классификация|термины и определения|коды по мкб)\s*[:.]?$", re.I)),
    ("diagnostics", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:диагностика(?: [а-я]+)?|жалобы|анамнез(?: [а-я]+)?|"
                               r"физикальное обследование|лабораторные диагностические исследования|"
                               r"инструментальные диагностические исследования|"
                               r"дифференциальная диагностика|клиническая картина|критерии установления диагноза)\s*[:.]?$", re.I)),
    ("treatment", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:лечение(?: [а-я]+)*|терапия|"
                             r"немедикаментозное лечение|медикаментозное лечение|хирургическое лечение|"
                             r"реабилитация|обезболивание)\s*[:.]?$", re.I)),
    ("referral_criteria", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:организация оказания медицинской помощи|"
                                     r"показания (?:к|для) госпитализации[а-я ]*|показания к оперативному лечению|"
                                     r"направление[а-я ]*)\s*[:.]?$", re.I)),
    ("prevention", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:профилактика(?: [а-я]+)*|"
                              r"диспансерное наблюдение(?: [а-я]+)*|вакцинопрофилактика)\s*[:.]?$", re.I)),
    ("complications", re.compile(r"^(?:\d+(?:\.\d+)*\.?\s*)?(?:осложнения|прогноз|"
                                 r"исходы заболевания|неблагоприятные[а-я ]*)\s*[:.]?$", re.I)),
]


# Мусор вёрстки, который не должен становиться «источником» для врача:
# колонтитулы с датой печати, крошки MedElement, URL, номера страниц.
_FURNITURE_RX = [
    re.compile(r"^\s*\d{1,2}\.\d{2}\.\d{4}[,.]?\s*\d{0,2}:?\d{0,2}\s*$"),
    re.compile(r">\s*Клинические рекомендации|medelement|diseases\.medelement", re.I),
    re.compile(r"https?://|www\.", re.I),
    re.compile(r"^\s*\d{1,3}\s*$"),
]
# Список литературы: целиком выбрасываем из индекса (это не клинический текст,
# но именно он раньше попадал в выдачу как «источник» с чужим разделом).
_REFERENCES_HEADING = re.compile(
    r"^\s*(?:список литературы|список источников|источники и литература|references|библиографи[а-я]*|литература)\s*[:.]?$", re.I)
_REF_LINE = re.compile(
    r"(?:doi:|https?://doi|\bet al\.|С\.\s*\d+\s*[-–]\s*\d+|"
    r"^\s*[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]?\.|^\s*\d{1,3}\.\s*[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.)", re.I)


def _is_furniture(line: str) -> bool:
    return any(rx.search(line) for rx in _FURNITURE_RX)


def _is_reference_line(line: str) -> bool:
    return bool(_REF_LINE.search(line))


def _section_of_line(line: str) -> str | None:
    """Раздел, если строка — заголовок главы (строго, целиком)."""
    ln = (line or "").strip()
    if not ln or len(ln) > 90:
        return None
    for sec, rx in _HEADING_RX:
        if rx.match(ln):
            return sec
    return None


def build_index_chunks(pages: list[dict]) -> list[dict]:
    """Чанки для поискового индекса: документ покрывается РОВНО ОДИН РАЗ,
    каждый чанк помечен своим разделом и реальными страницами.

    Прежняя схема индексировала три раздела (обрезанных до 6000 символов) плюс
    весь текст целиком — 84 % корпуса оказывались дублями `general` (1304 из
    1599 чанков), они вытесняли из топ-6 нужный раздел, и модель отвечала
    «в контексте нет информации». Замер: docs/RETRIEVAL_EVAL.md.
    """
    segments: list[dict] = []  # {section, lines, pages}
    cur, buf, pages_seen = "general", [], set()

    def flush():
        if buf:
            segments.append({"section": cur, "lines": list(buf), "pages": sorted(pages_seen)})
            buf.clear()
            pages_seen.clear()

    for p in pages:
        page_no = p.get("page", 1)
        for ln in (p.get("text") or "").split("\n"):
            if _is_furniture(ln) or _is_reference_line(ln):
                continue  # колонтитулы и библиография в индекс не идут
            if _REFERENCES_HEADING.match(ln.strip()):
                flush()
                cur = "references"
                continue
            hit = _section_of_line(ln)
            if hit and hit != cur:
                flush()
                cur = hit
                continue
            buf.append(ln)
            pages_seen.add(page_no)
    flush()

    chunks: list[dict] = []
    for seg in segments:
        if seg["section"] == "references":
            continue
        text = "\n".join(seg["lines"])
        if len(text.strip()) < 40:
            continue
        for ch in chunk_text(text, {"section": seg["section"]}):
            chunks.append({**ch, "page_range": seg["pages"][:10] or [1]})
    return chunks

def process_pdf(path: str, llm_client=None, title: str | None = None) -> dict:
    import os
    pages = load_pages(path)
    secs = detect_sections(pages)
    full = secs.get("raw", "")
    icd = extract_icd10(full)
    tables = parse_tables(path)
    llm_part = {"definition": secs.get("definition", "")[:2000]}
    if llm_client:
        from .llm_structurer import structure_with_llm
        try: llm_part = structure_with_llm(full[:8000], llm_client)
        except Exception: pass
    year_m = re.search(r"(19|20)\d{2}", os.path.basename(path))
    found = secs.get("sections_found", [])
    # Тихо терять данные запрещено: если секции не распознались (нестандартные
    # заголовки) или нет кодов МКБ — документ уходит на ручную проверку.
    needs_review = not bool(icd and full.strip()) or len(found) < 2
    conf = "high" if (icd and len(full) > 3000 and len(found) >= 3) else (
        "medium" if (full.strip() and not needs_review) else (
            "medium" if (full.strip() and len(found) >= 1) else "low"))
    if not full.strip():
        conf, needs_review = "low", True
    doc = {
        "document_id": str(uuid.uuid4()),
        "title": title or os.path.basename(path)[:200],
        "nosology": (title or os.path.basename(path).split("_")[0].split(".")[0])[:200],
        "icd10_codes": icd,
        "approval_year": int(year_m.group(0)) if year_m else 2024,
        "revision_year": None,
        "source_file": os.path.basename(path),
        "processing_status": "processed" if full.strip() else "failed",
        "sections": {
            "definition": llm_part.get("definition") or secs.get("definition", ""),
            "etiology_epidemiology": str(llm_part.get("etiology_epidemiology") or ""),
            "classification": str(llm_part.get("classification") or ""),
            "diagnostics": {"complaints": [], "anamnesis": [], "physical_exam": [],
                            "lab_tests": [], "instrumental_tests": [],
                            "differential_diagnosis": [], "raw": secs.get("diagnostics", "")},
            "treatment": {"conservative": tables[:20], "surgical": [],
                          "indications_for_hospitalization": [],
                          "raw": secs.get("treatment", "")},
            "complications": [], "prevention": [], "prognosis": [],
            "referral_criteria": [], "follow_up": [],
        },
        "source_pages": secs.get("source_pages", {}),
        "extraction_confidence": conf,
        "needs_manual_review": needs_review,
    }
    # чанки для RAG
    chunks = []
    for sec_name in ("definition", "diagnostics", "treatment"):
        t = secs.get(sec_name, "")
        if isinstance(t, dict): t = t.get("raw", "")
        chunks += chunk_text(str(t), {"section": sec_name,
            "page_range": doc["source_pages"].get(sec_name, [1])})
    # плюс общие чанки ПО ВСЕМУ документу (дозы/факты в конце не должны теряться)
    chunks += chunk_text(full, {"section": "general", "page_range": sorted(
        {p["page"] for p in pages})[:10] or [1]})
    doc["_chunks"] = chunks
    doc["_full_text"] = full[:60000]
    return doc
