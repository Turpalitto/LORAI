"""Детерминированный парсинг таблиц дозировок (НЕ отправлять в LLM)."""
def parse_tables(path: str) -> list[dict]:
    try:
        import pdfplumber
        out = []
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                for t in (page.extract_tables() or []):
                    if not t or len(t) < 2: continue
                    header = [str(c or "").strip().lower() for c in t[0]]
                    # эвристика: таблица с дозами если в шапке есть доза/мг/мл
                    if any(k in " ".join(header) for k in ("доз", "мг", "препарат", "drug", "dose")):
                        for row in t[1:]:
                            out.append({"page": i + 1, "header": t[0], "row": row})
        return out
    except Exception:
        return []
