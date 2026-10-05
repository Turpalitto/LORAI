"""Дифдиагностика: взвешенное ранжирование по патогномоничности (Excellence-1).

Было: score = доля совпавших симптомов (все симптомы равнозначны).
Стало: вес симптома = IDF по корпусу протоколов — редкий, специфичный
признак (например, «парез лицевого нерва») весит больше, чем общий
(«боль», «лихорадка»). К топ-1 прикладывается объяснение «почему именно
эта нозология на первом месте».
"""
import math


def _hay(p: dict) -> str:
    return (str(p.get("sections", "")) + " " + p.get("nosology", "")).lower()


def rank(symptoms: list[str], protocols: list[dict]) -> list[dict]:
    syms = [s for s in (symptoms or []) if s and s.strip()]
    if not syms or not protocols:
        return []
    hays = [_hay(p) for p in protocols]
    N = len(protocols)
    weights = {}
    for s in syms:
        df = sum(1 for h in hays if s.lower() in h)
        weights[s] = math.log(1 + N / (1 + df)) if df else math.log(1 + N)
    res = []
    for p, hay in zip(protocols, hays):
        hits = [s for s in syms if s.lower() in hay]
        if not hits:
            continue
        score = sum(weights[s] for s in hits)
        rare = sorted(hits, key=lambda s: -weights[s])[:2]
        total_w = sum(weights.values()) or 1
        res.append(
            {
                "nosology": p["nosology"],
                "title": p["title"],
                "matched": hits,
                "score": round(score / total_w, 2),
                "icd10": p.get("icd10_codes", []),
                "key_signs": rare,
                "explanation": (
                    f"Решающие признаки: {', '.join(rare)} — "
                    f"совпало {len(hits)} из {len(syms)}"
                ),
            }
        )
    res.sort(key=lambda x: -x["score"])
    if res:
        top = res[0]
        top["why_first"] = (
            f"«{top['nosology']}» на первом месте: наибольший суммарный вес "
            f"совпавших признаков ({top['score']}), ключевой — "
            f"«{top['key_signs'][0]}». Решение принимает врач."
        )
    return res
