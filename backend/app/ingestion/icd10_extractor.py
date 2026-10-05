import re
# Буква+2 цифры (+подкод). Отрицательный просмотр вперёд отсекает ATC-коды
# типа D08AJ и прочие слитные буквенно-цифровые токены (не МКБ).
PAT = re.compile(r"\b([A-TV-Z]\d{2}(?:\.\d{1,2})?)(?![A-Za-zА-Яа-я0-9])")
# базовый офлайн-список ЛОР-кодов
LOR_RANGES = [("H60","H95"),("J00","J39"),("C30","C32"),("C73","C73")]
# контекст, в котором совпадение паттерна — заведомо НЕ код МКБ (витамины и т.п.)
FALSE_CTX = re.compile(r"витамин[а-я]*\s*$", re.IGNORECASE)
def extract_icd10(text: str) -> list[str]:
    codes = set()
    text = text or ""
    for m in PAT.finditer(text):
        start = max(0, m.start() - 25)
        prefix = text[start:m.start()] or ""
        suffix = text[m.end():m.end()+5] or ""
        code = m.group(1)
        # «витамин B12» — не диагноз, пропускаем
        if FALSE_CTX.search(prefix):
            continue
        # «Код АТХ: D08», «АТХ-N06» — фармакологический классификатор, не МКБ
        if re.search(r"АТ[ХX]\s*[-:]?\s*$", prefix):
            continue
        # «(R06: Антигистаминные…» — подпись группы АТХ, не диагноз
        if re.search(r"\(\s*$", prefix) and re.search(r"^\s*:", suffix):
            continue
        # Номенклатура медуслуг: A23.25.001, B01.041.001 — трёхзначная 3-я группа
        # (в МКБ-10 такого не бывает) — пропускаем усечённое совпадение целиком
        if re.match(r"\.\d", suffix):
            continue
        # E-страницы журналов в библиографии: 92(4-5):E10-2 — не диагноз
        if re.search(r"\(\d+(?:-\d+)?\)\s*:\s*$", prefix) and code.startswith("E"):
            continue
        # Номера supplement-страниц в библиографии: 38(S55), (S79), 39(5):S79 — не диагнозы
        if code.startswith("S") and (re.search(r"\([^)]{0,10}:?\s*$", prefix)
                                     or re.search(r"\(\d+\)\s*:\s*$", prefix)
                                     or re.search(r"suppl[^:]{0,14}\)\s*:\s*$", prefix, re.IGNORECASE)
                                     or re.search(r"suppl[^:()]{0,12}:\s*$", prefix, re.IGNORECASE)
                                     or re.search(r"S\d{1,2}\s*[-–]\s*$", prefix)):
            continue
        codes.add(code)
    return sorted(codes)
def is_lor(code: str) -> bool:
    p = code[:3]
    return any(lo <= p <= hi for lo, hi in LOR_RANGES)
