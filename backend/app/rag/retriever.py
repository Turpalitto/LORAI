import re
def classify_intent(q: str) -> str:
    l = q.lower()
    if re.search(r"доз|мг|мл|кг|вес|калькул", l): return "вопрос_по_дозировке"
    if re.search(r"диф|отличи|вероятн|симптом", l): return "дифдиагностика"
    if re.search(r"протокол|мкб|нозолог|критери|показани|госпитал", l): return "поиск_протокола"
    return "общий_вопрос"
