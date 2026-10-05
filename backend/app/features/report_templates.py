TEMPLATES = {
    "zaklyuchenie": "ЗАКЛЮЧЕНИЕ ЛОР-ВРАЧА\nНозология: {nosology} ({icd})\nЖалобы: ____\nОсмотр: ____\nДиагноз: ____\nРекомендации (по КР {title}, {year}): ____\nВрач: ____ / ____\nИнструмент справочный. Решение принимает врач.",
    "napravlenie": "НАПРАВЛЕНИЕ\nКуда: ____\nДиагноз: {nosology} {icd}\nОснование (критерии из КР {title}): ____\nВрач: ____\n",
}
def render(kind: str, protocol: dict) -> str:
    t = TEMPLATES.get(kind, TEMPLATES["zaklyuchenie"])
    return t.format(nosology=protocol.get("nosology",""), icd=",".join(protocol.get("icd10_codes",[])),
                    title=protocol.get("title",""), year=protocol.get("approval_year",""))
