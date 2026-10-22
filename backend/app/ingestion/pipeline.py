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

# Приложения КР (А1 — состав рабочей группы, А2 — методология, А3 — справочные
# материалы, Б — алгоритмы, В — для пациента, Г1-ГN — шкалы). Раньше они не
# распознавались и наследовали раздел последней главы: 109 чанков из 1073 (10 %)
# лежали в `definition`/`treatment` и получали буст по запросу «как лечить»,
# выдавая «Состав рабочей группы» как источник по тактике.
# Берём только буквенную форму («Приложение А1.», «Приложение Г1-ГN.»):
# цифровая («Приложение 3 приказа Минздрава») — это ссылка на чужой документ,
# а не раздел этого.
_APPENDIX_HEADING = re.compile(
    r"^\s*приложение\s+[а-яёa-z][а-яёa-z\d\s.\-–]{0,10}?(?:\.|$)", re.I)


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


# Заголовок, подтверждённый ВЁРСТКОЙ (крупный кегль, см. pdf_loader._page_headings),
# можно трактовать мягче: не «строка целиком равна названию главы», а «в коротком
# заголовке есть ключевое слово». Именно так терялись «Медицинская реабилитация»,
# «Клиническая картина», «Cимптомы, течение» — они реальные главы, но строгий
# regex требовал совпадения всей строки.
_HEADING_KEYS = [
    ("definition", re.compile(r"определен|этиологи|патогенез|классификац|эпидемиологи|"
                              r"краткое описание|общая информация|термин", re.I)),
    ("diagnostics", re.compile(r"диагностик|клиническая картина|[cс]имптом|жалоб|осмотр|"
                               r"обследован|анамнез", re.I)),
    ("treatment", re.compile(r"лечен|терапи|реабилитац|оперативн|хирург", re.I)),
    ("referral_criteria", re.compile(r"госпитализац|направлен|организация оказания", re.I)),
    ("prevention", re.compile(r"профилактик|диспансерн|вакцин", re.I)),
    ("complications", re.compile(r"осложнен|прогноз|исходы заболевания", re.I)),
]


def _section_of_heading(line: str) -> str | None:
    """Раздел по заголовку, распознанному по шрифту (мягкое правило)."""
    ln = (line or "").strip()
    if not ln or len(ln) > 120:
        return None
    for sec, rx in _HEADING_KEYS:
        if rx.search(ln):
            return sec
    return None


def _norm_line(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


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
        # Заголовки этой страницы, подтверждённые вёрсткой (может не быть: txt,
        # скан, старая версия лоадера). Сравниваем по нормализованному тексту.
        page_heads = {_norm_line(h) for h in (p.get("headings") or []) if h}
        for ln in (p.get("text") or "").split("\n"):
            if _is_furniture(ln) or _is_reference_line(ln):
                continue  # колонтитулы и библиография в индекс не идут
            # Приложение проверяем ДО библиографии: приложения идут после списка
            # литературы, и без этой ветки они оставались в разделе `references`
            # (то есть выбрасывались) либо наследовали раздел последней главы.
            if _APPENDIX_HEADING.match(ln.strip()):
                flush()
                cur = "appendix"
                continue
            if _REFERENCES_HEADING.match(ln.strip()):
                flush()
                cur = "references"
                continue
            if page_heads and _norm_line(ln) in page_heads:
                hit = _section_of_heading(ln) or _section_of_line(ln)
            else:
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

def _section_text(chunks: list[dict], name: str, cap: int = 20000) -> str:
    """Текст раздела из чанков — тот же, что уходит в поисковый индекс.
    Раньше разделы собирались отдельной эвристикой (`detect_sections`) и
    обрезались до 6000 символов: чек-лист и поиск видели разный текст."""
    parts = [c.get("text", "") for c in chunks if c.get("section") == name]
    return "\n".join(parts)[:cap]


def process_pdf(path: str, llm_client=None, title: str | None = None,
                document_id: str | None = None) -> dict:
    """Разбор PDF/TXT в документ + чанки.

    `document_id` задаётся снаружи при фоновой обработке: запись создаётся
    заранее (status=processing), чтобы клиент мог опрашивать статус, а
    результат лёг в ту же строку.
    """
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

    # Чанки — тем же чанкером, что и офлайн-пересборка корпуса (1.3.0).
    # Раньше загрузка через админку шла старым путём: разделы обрезались до
    # 6000 символов, а «общие» чанки дублировали весь документ (замер на КР
    # «Аллергический ринит»: 88 % чанков — general против 2 % у нового чанкера).
    # Новый документ, загруженный врачом, попадал в индекс в худшем виде, чем
    # тот же документ после scripts/reindex_corpus.py.
    chunks = build_index_chunks(pages)
    if not chunks and full.strip():
        # короткий/нестандартный документ: не теряем текст совсем
        chunks = chunk_text(full, {"section": "general",
                                   "page_range": sorted({p["page"] for p in pages})[:10] or [1]})
    found = sorted({c.get("section", "") for c in chunks if c.get("section") not in ("", "general")})

    # Тихо терять данные запрещено: если секции не распознались (нестандартные
    # заголовки) или нет кодов МКБ — документ уходит на ручную проверку.
    needs_review = not bool(icd and full.strip()) or len(found) < 2
    conf = "high" if (icd and len(full) > 3000 and len(found) >= 3) else (
        "medium" if (full.strip() and not needs_review) else (
            "medium" if (full.strip() and len(found) >= 1) else "low"))
    if not full.strip():
        conf, needs_review = "low", True
    doc = {
        "document_id": document_id or str(uuid.uuid4()),
        "title": title or os.path.basename(path)[:200],
        # .strip(): заголовок берётся с первой страницы PDF и почти всегда
        # приходит с хвостовым переводом строки/пробелом — из-за этого фильтр
        # по нозологии в API не находил ни одного чанка (см. vector_store._norm_nos).
        "nosology": (title or os.path.basename(path).split("_")[0].split(".")[0]).strip()[:200],
        "icd10_codes": icd,
        "approval_year": int(year_m.group(0)) if year_m else 2024,
        "revision_year": None,
        "source_file": os.path.basename(path),
        "processing_status": "processed" if full.strip() else "failed",
        "sections": {
            "definition": llm_part.get("definition") or _section_text(chunks, "definition"),
            "etiology_epidemiology": str(llm_part.get("etiology_epidemiology") or ""),
            "classification": str(llm_part.get("classification") or ""),
            "diagnostics": {"complaints": [], "anamnesis": [], "physical_exam": [],
                            "lab_tests": [], "instrumental_tests": [],
                            "differential_diagnosis": [],
                            "raw": _section_text(chunks, "diagnostics")},
            "treatment": {"conservative": tables[:20], "surgical": [],
                          "indications_for_hospitalization": [],
                          "raw": _section_text(chunks, "treatment")},
            "complications": _section_text(chunks, "complications"),
            "prevention": _section_text(chunks, "prevention"),
            "prognosis": [],
            "referral_criteria": _section_text(chunks, "referral_criteria"),
            "follow_up": [],
        },
        "source_pages": secs.get("source_pages", {}),
        "extraction_confidence": conf,
        "needs_manual_review": needs_review,
    }
    doc["_chunks"] = chunks
    doc["_full_text"] = full[:60000]
    return doc
