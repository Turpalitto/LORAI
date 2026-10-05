"""Клинические калькуляторы (Excellence-5): строго детерминированная
математика по опубликованным шкалам. Никакого LLM — только формулы.
Результат всегда сопровождается дисклеймером на уровне эндпоинта."""


def centor(fever: bool, exudate: bool, nodes: bool, no_cough: bool,
           age_band: str) -> dict:
    """Шкала Centor/McIsaac для фарингита (0–5 баллов с поправкой на возраст)."""
    if age_band not in ("3-14", "15-44", "45+"):
        raise ValueError("age_band должен быть одним из: 3-14, 15-44, 45+")
    score = sum((bool(fever), bool(exudate), bool(nodes), bool(no_cough)))
    score += {"3-14": 1, "15-44": 0, "45+": -1}[age_band]
    score = max(0, min(5, score))
    if score <= 1:
        interp = "Низкая вероятность стрептококкового фарингита"
        rec = "Симптоматическое лечение; тест/посев обычно не требуется."
    elif score == 2:
        interp = "Промежуточная вероятность"
        rec = "Экспресс-тест на стрептококк группы А или посев; решение по результату."
    else:
        interp = "Высокая вероятность стрептококкового фарингита"
        rec = "Экспресс-тест/посев; при подтверждении — антибиотик по протоколу."
    return {"scale": "centor_mcisaac", "score": score, "max": 5,
            "interpretation": interp, "recommendation": rec}


def pta(thresholds_db: list[float]) -> dict:
    """Средний порог слуха (PTA 0.5/1/2/4 кГц) и степень потери (ВОЗ)."""
    if len(thresholds_db) != 4:
        raise ValueError("Нужно ровно 4 порога: 500/1000/2000/4000 Гц")
    for v in thresholds_db:
        if not -10 <= v <= 120:
            raise ValueError(f"Порог {v} дБ вне диапазона -10..120")
    avg = round(sum(thresholds_db) / 4, 1)
    if avg <= 25:
        grade = "Норма"
    elif avg <= 40:
        grade = "Лёгкая потеря слуха"
    elif avg <= 60:
        grade = "Умеренная потеря слуха"
    elif avg <= 80:
        grade = "Тяжёлая потеря слуха"
    else:
        grade = "Глубокая потеря слуха"
    return {"scale": "pta_500_1000_2000_4000", "average_db": avg,
            "grade": grade,
            "recommendation": "Степень ориентировочная; тактику определяет врач по аудиограмме."}
