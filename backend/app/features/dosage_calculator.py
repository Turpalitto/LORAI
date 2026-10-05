import re
def calc_dose(weight_kg: float, mg_per_kg: float, max_mg: float | None = None, freq: str = "") -> dict:
    dose = weight_kg * mg_per_kg
    if max_mg: dose = min(dose, max_mg)
    return {"weight_kg": weight_kg, "mg_per_kg": mg_per_kg, "single_dose_mg": round(dose, 1),
            "max_mg": max_mg, "frequency": freq,
            "warning": "Сверьте с протоколом. Решение принимает врач."}
def parse_mg_per_kg(formula: str) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*мг/кг", formula or "")
    return float(m.group(1).replace(",", ".")) if m else None
