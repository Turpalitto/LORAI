"""Расчёт разовой и суточной дозы по весу.

Формула простая и намеренно «тупая»: вес × мг/кг, с потолком разовой дозы.
Всё, что связано с кратностью, берётся из разбора текста (app/clinical) —
чтобы «3 раза в сутки» превращалось в суточную дозу, а не оставалось строкой.
"""
import re


def calc_dose(weight_kg: float, mg_per_kg: float, max_mg: float | None = None,
              freq: str = "", doses_per_day: float | None = None) -> dict:
    dose = weight_kg * mg_per_kg
    capped = False
    if max_mg and dose > max_mg:
        dose, capped = max_mg, True
    out = {
        "weight_kg": weight_kg,
        "mg_per_kg": mg_per_kg,
        "single_dose_mg": round(dose, 1),
        "max_mg": max_mg,
        "capped": capped,
        "frequency": freq,
        "doses_per_day": doses_per_day,
        "daily_mg": round(dose * doses_per_day, 1) if doses_per_day else None,
        "warning": "Сверьте с протоколом. Решение принимает врач.",
    }
    return out


def parse_mg_per_kg(formula: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*мг/кг", formula or "")
    return float(m.group(1).replace(",", ".")) if m else None
