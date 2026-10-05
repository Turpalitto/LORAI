"""Дифдиагностика: взвешенное ранжирование по патогномоничности (Excellence-1).

Было: score = доля совпавших симптомов (все симптомы равнозначны).
Стало: вес симптома = IDF по корпусу протоколов — редкий, специфичный
признак (например, «парез лицевого нерва») весит больше, чем общий
(«боль», «лихорадка»). К топ-1 прикладывается объяснение «почему именно
эта нозология на первом месте».
"""
import math
import re


def _hay(p: dict) -> str:
    return (str(p.get("sections", "")) + " " + p.get("nosology", "")).lower()


def _tok(s: str) -> list[str]:
    return [t for t in re.findall(r"[а-яa-z0-9]+", (s or "").lower()) if len(t) >= 4]


def _matches(symptom: str, hay: str) -> bool:
    """Токенное совпадение: хватило половины значимых слов симптома.
    Точная фраза («тризм жевательных мышц») редко дословно есть в тексте
    («тризм жевательной мускулатуры»), а слова — есть."""
    toks = _tok(symptom)
    if not toks:
        return symptom.lower() in hay
    need = max(1, len(toks) // 2)
    return sum(1 for t in toks if t in hay) >= need


def rank(symptoms: list[str], protocols: list[dict]) -> list[dict]:
    syms = [s for s in (symptoms or []) if s and s.strip()]
    if not syms or not protocols:
        return []
    hays = [_hay(p) for p in protocols]
    N = len(protocols)
    weights = {}
    for s in syms:
        df = sum(1 for h in hays if _matches(s, h))
        weights[s] = math.log(1 + N / (1 + df)) if df else math.log(1 + N)
    res = []
    for p, hay in zip(protocols, hays):
        hits = [s for s in syms if _matches(s, hay)]
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
