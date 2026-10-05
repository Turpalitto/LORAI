import re
PAT = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)\b")
# базовый офлайн-список ЛОР-кодов
LOR_RANGES = [("H60","H95"),("J00","J39"),("C30","C32"),("C73","C73")]
def extract_icd10(text: str) -> list[str]:
    codes = sorted(set(PAT.findall(text)))
    return codes
def is_lor(code: str) -> bool:
    p = code[:3]
    return any(lo <= p <= hi for lo, hi in LOR_RANGES)
