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
        "extraction_confidence": "high" if (icd and len(full) > 3000) else ("medium" if full.strip() else "low"),
        "needs_manual_review": not bool(icd and full.strip()),
    }
    # чанки для RAG
    chunks = []
    for sec_name in ("definition", "diagnostics", "treatment"):
        t = secs.get(sec_name, "")
        if isinstance(t, dict): t = t.get("raw", "")
        chunks += chunk_text(str(t), {"section": sec_name,
            "page_range": doc["source_pages"].get(sec_name, [1])})
    # плюс общий чанк начала документа
    chunks += chunk_text(full[:6000], {"section": "general", "page_range": [1, 2, 3]})
    doc["_chunks"] = chunks
    doc["_full_text"] = full[:20000]
    return doc
