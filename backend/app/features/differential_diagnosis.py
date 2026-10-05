"""Дифдиагностика: ранжирование нозологий по совпадению симптомов."""
def rank(symptoms: list[str], protocols: list[dict]) -> list[dict]:
    res = []
    for p in protocols:
        hay = str(p.get("sections", "")).lower() + p.get("nosology","").lower()
        hits = [s for s in symptoms if s.lower() in hay]
        if hits: res.append({"nosology": p["nosology"], "title": p["title"],
            "matched": hits, "score": round(len(hits)/max(1,len(symptoms)),2),
            "icd10": p.get("icd10_codes",[])})
    return sorted(res, key=lambda x: -x["score"])
