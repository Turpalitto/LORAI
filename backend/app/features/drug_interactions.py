"""Проверка лекарственных взаимодействий строго по текстам протоколов (Excellence-1).

Принцип: никакого домысливания фармакологии вне базы знаний. Модуль ищет
в найденных чанках предложения с маркерами противопоказаний/взаимодействий
и возвращает их как цитаты с атрибуцией документа. Если в протоколах про
комбинацию ничего нет — честно сообщает об отсутствии данных.
"""
import re

CUE_RX = re.compile(
    r"[^.]*?(противопоказан|несовместим|взаимодействи|не сочетать|нельзя сочетать|"
    r"с осторожностью|снижает эффект|усиливает (?:эффект|действие)|"
    r"повышает риск|не рекомендуется (?:совмест|комбини))[^.]*\.",
    re.I,
)


def find_warnings(drug: str, chunks: list[dict]) -> list[dict]:
    """Предложения-предупреждения о препарате из чанков с атрибуцией."""
    out = []
    dl = drug.lower()
    for c in chunks:
        if dl not in (c.get("text") or "").lower():
            continue
        for m in CUE_RX.finditer(c.get("text") or ""):
            out.append(
                {
                    "drug": drug,
                    "quote": m.group(0).strip()[:400],
                    "document": c.get("document", ""),
                    "section": c.get("section", ""),
                }
            )
    return out[:5]


def check_combination(drugs: list[str], search_fn) -> dict:
    """search_fn(drug) -> list[chunks]. Возвращает цитаты и честный вердикт."""
    drugs = [d.strip() for d in drugs if d and d.strip()][:6]
    per_drug: dict[str, list[dict]] = {}
    for d in drugs:
        per_drug[d] = find_warnings(d, search_fn(d))
    pairs_with_data = [d for d, w in per_drug.items() if w]
    if not pairs_with_data:
        verdict = (
            "В загруженных клинических рекомендациях данных о взаимодействии "
            "указанных препаратов не найдено. Решение принимает врач."
        )
    else:
        verdict = (
            "Найдены упоминания предостережений в протоколах "
            f"(по препаратам: {', '.join(pairs_with_data)}). "
            "Проверьте цитаты ниже. Решение принимает врач."
        )
    return {"per_drug": per_drug, "verdict": verdict}
