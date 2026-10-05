import re
PAT = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)\b")
# базовый офлайн-список ЛОР-кодов
LOR_RANGES = [("H60","H95"),("J00","J39"),("C30","C32"),("C73","C73")]
# контекст, в котором совпадение паттерна — заведомо НЕ код МКБ (витамины и т.п.)
FALSE_CTX = re.compile(r"витамин[а-я]*\s*$", re.IGNORECASE)
def extract_icd10(text: str) -> list[str]:
    codes = set()
    for m in PAT.finditer(text or ""):
        start = max(0, m.start() - 20)
        prefix = (text[start:m.start()] or "")
        # «витамин B12» — не диагноз, пропускаем
        if FALSE_CTX.search(prefix):
            continue
        codes.add(m.group(1))
    return sorted(codes)
def is_lor(code: str) -> bool:
    p = code[:3]
    return any(lo <= p <= hi for lo, hi in LOR_RANGES)
