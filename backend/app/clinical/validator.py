"""Вердикт по разобранной схеме: PASS / REVIEW / REJECT.

Перенесено по мотивам `REGIMEN_VALIDATION_GATES.md` из antibio-calc (гейты
1–3: обязательные поля, целостность, клиническая безопасность). Там это
проектная спецификация для ассемблера схем; здесь — компактная детерминированная
реализация для того, что LORAI реально умеет проверить без LLM.

Главное правило (унаследовано и не обсуждается): **валидатор умеет только
понижать вердикт**. Ни одна проверка не может превратить REVIEW в PASS.
PASS ставится лишь тогда, когда пройдены все проверки — иначе «зелёный»
вердикт на неполной схеме читается врачом как «проверено и безопасно».

Чего здесь намеренно НЕТ:
  * потолков доз по конкретным препаратам — в LORAI нет сертифицированной
    таблицы максимальных доз, а выдумать её значит дать ложную уверенность.
    Верхняя граница передаётся вызывающей стороной (`max_single_mg` /
    `max_daily_mg`), как в `/dosage`;
  * проверки взаимодействий — данных о взаимодействиях в корпусе нет
    (в antibio-calc этот гейт тоже помечен как невыполнимый);
  * беременности, почечной функции, возраста — этих полей в разборе нет,
    и «по умолчанию безопасно» здесь не подставляется.
"""
from __future__ import annotations

PASS = "PASS"
REVIEW = "REVIEW"
REJECT = "REJECT"

_RANK = {PASS: 0, REVIEW: 1, REJECT: 2}

# Грубая защита от ошибки разбора, а не клинический потолок: 5000 мг разово —
# это либо опечатка в протоколе, либо склеенная строка таблицы. Такое нельзя
# показывать как «схема проверена», даже если формально все поля на месте.
ABSURD_SINGLE_MG = 5000.0
# Больше 8 приёмов в сутки для системного препарата — почти наверняка ошибка
# разбора («каждые 2 часа» из инструкции по применению капель).
MAX_DOSES_PER_DAY = 8.0
# Курс длиннее 90 дней — либо хроническая терапия, либо не тот абзац.
MAX_DURATION_DAYS = 90.0

POLICY = ("Валидатор может только понижать вердикт: PASS — все проверки пройдены, "
          "REVIEW — есть что проверить врачом, REJECT — схема непригодна как есть.")


def _check(name: str, status: str, code: str, message: str, **detail) -> dict:
    return {"name": name, "status": status, "code": code, "message": message, **detail}


def validate_regimen(regimen: dict, *, weight_kg: float | None = None,
                     max_single_mg: float | None = None,
                     max_daily_mg: float | None = None) -> dict:
    """Проверить разобранную схему (`parse_regimen`) и вернуть вердикт.

    `weight_kg` нужен только для доз «мг/кг»: без веса разовую дозу в мг
    посчитать нельзя, и это REVIEW, а не «примерно 70 кг».
    """
    dose = regimen.get("dose") or {}
    freq = regimen.get("frequency") or {}
    dur = regimen.get("duration") or {}
    drug = regimen.get("drug") or {}

    checks: list[dict] = []

    # 1. Препарат. Свободный текст вместо распознанного МКН — не рекомендация.
    if drug.get("normalized"):
        checks.append(_check("drug", PASS, "drug_ok",
                             f"Препарат распознан: {drug['normalized']}"))
    else:
        checks.append(_check("drug", REJECT, "drug_unrecognized",
                             "Препарат не распознан по словарю МКН — схему нельзя "
                             "использовать как рекомендацию."))

    # 2. Доза. Ни мг, ни мг/кг — считать нечего.
    if dose.get("value") is None:
        checks.append(_check("dose", REJECT, "dose_missing", "Доза в тексте не найдена."))
    elif not dose.get("per_kg") and dose.get("mg") is None:
        checks.append(_check("dose", REVIEW, "dose_unit_not_mass",
                             f"Доза задана в «{dose.get('unit') or '?'}» — в мг не "
                             "переводится, суточную дозу не посчитать."))
    else:
        checks.append(_check("dose", PASS, "dose_ok",
                             f"Доза найдена: {dose.get('raw') or dose.get('value')}"))

    # 3. Разовая доза в мг: пересчёт по весу или прямое значение.
    single_mg: float | None = None
    if dose.get("per_kg"):
        if weight_kg and weight_kg > 0:
            single_mg = round(float(dose["value"]) * float(weight_kg), 1)
            checks.append(_check("weight_basis", PASS, "weight_given",
                                 f"Доза на кг пересчитана по весу {weight_kg} кг: "
                                 f"{single_mg} мг разово."))
        else:
            checks.append(_check("weight_basis", REVIEW, "weight_required",
                                 "Доза указана на кг массы — без веса пациента "
                                 "разовую дозу не посчитать."))
    elif dose.get("mg") is not None:
        single_mg = float(dose["mg"])

    # 4. Потолок разовой дозы: переданный извне или грубая проверка на абсурд.
    if single_mg is not None:
        if max_single_mg and single_mg > max_single_mg:
            checks.append(_check("single_ceiling", REVIEW, "above_max_single",
                                 f"Разовая доза {single_mg} мг выше заданного потолка "
                                 f"{max_single_mg} мг — сверьте с протоколом."))
        elif single_mg > ABSURD_SINGLE_MG:
            checks.append(_check("single_ceiling", REVIEW, "implausible_single_dose",
                                 f"Разовая доза {single_mg} мг выглядит как ошибка "
                                 "разбора — проверьте текст."))
        else:
            checks.append(_check("single_ceiling", PASS, "single_ok",
                                 f"Разовая доза {single_mg} мг в разумных пределах."))

    # 5. Кратность. Без неё суточная доза не считается.
    per_day = freq.get("per_day")
    if per_day is None:
        checks.append(_check("frequency", REVIEW, "frequency_missing",
                             "Кратность не распознана — суточную дозу не посчитать."))
    elif per_day > MAX_DOSES_PER_DAY:
        checks.append(_check("frequency", REVIEW, "frequency_implausible",
                             f"{per_day} приёмов в сутки — похоже на ошибку разбора."))
    else:
        checks.append(_check("frequency", PASS, "frequency_ok",
                             f"Кратность: {per_day} раз в сутки."))

    # 6. Курс.
    days = dur.get("recommended_days")
    if days is None:
        checks.append(_check("duration", REVIEW, "duration_missing",
                             "Курс не указан — длительность лечения не проверена."))
    elif days > MAX_DURATION_DAYS:
        checks.append(_check("duration", REVIEW, "duration_implausible",
                             f"Курс {days} дней — либо хроническая терапия, либо "
                             "разобрана не та фраза."))
    else:
        checks.append(_check("duration", PASS, "duration_ok", f"Курс: {days} дн."))

    # 7. Путь введения.
    route = (regimen.get("route") or "unknown")
    if route == "unknown":
        checks.append(_check("route", REVIEW, "route_missing",
                             "Путь введения не распознан."))
    else:
        checks.append(_check("route", PASS, "route_ok", f"Путь введения: {route}."))

    # 8. Диапазоны. Взята нижняя граница — это осознанный компромисс разбора,
    # но врач должен знать, что в протоколе написано «2–3 раза».
    ranges = [name for name, block in (("кратность", freq), ("курс", dur))
              if block.get("is_range")]
    if ranges:
        checks.append(_check("ranges", REVIEW, "range_lower_bound",
                             f"Диапазон в поле «{', '.join(ranges)}» — взята нижняя "
                             "граница, сверьте с текстом."))
    else:
        checks.append(_check("ranges", PASS, "no_ranges", "Диапазонов в схеме нет."))

    # 9. Суточная доза против переданного потолка.
    daily_mg: float | None = None
    if single_mg is not None and per_day:
        daily_mg = round(single_mg * per_day, 1)
    if daily_mg is not None and max_daily_mg and daily_mg > max_daily_mg:
        checks.append(_check("daily_ceiling", REVIEW, "above_max_daily",
                             f"Суточная доза {daily_mg} мг выше заданного потолка "
                             f"{max_daily_mg} мг."))
    elif daily_mg is not None:
        checks.append(_check("daily_ceiling", PASS, "daily_ok",
                             f"Суточная доза: {daily_mg} мг."))

    verdict = max((c["status"] for c in checks), key=lambda s: _RANK[s])
    return {
        "verdict": verdict,
        "checks": checks,
        "reasons": [{"code": c["code"], "status": c["status"], "message": c["message"]}
                    for c in checks if c["status"] != PASS],
        "computed": {"single_mg": single_mg, "daily_mg": daily_mg,
                     "weight_kg": weight_kg, "doses_per_day": per_day},
        "limits": {"max_single_mg": max_single_mg, "max_daily_mg": max_daily_mg},
        "policy": POLICY,
        "note": "Вердикт не заменяет проверку врачом: PASS значит «формально полная "
                "схема», а не «назначение верно».",
    }
