"""Детерминированный разбор схемы антибиотикотерапии из текста клинрекомендации.

Источник правил: antibio-calc/medical_normalizer (frequency_parser,
duration_parser, dictionary), проверенный на корпусе КР Минздрава. Здесь
оставлена только та часть, которая нужна LORAI: привести препарат к МКН
(международному непатентованному наименованию), разобрать дозу, кратность,
курс и путь введения.

Принципы (унаследованы от antibio-calc, менять нельзя):
  * диапазон («2–3 раза», «7–10 дней») → берём НИЖНЮЮ границу и флаг is_range.
    Верхняя граница при расчёте дозы — путь к передозировке;
  * ничего не додумываем: нет данных → None, а не «среднее по больнице»;
  * единицы массы (г/мг/мкг) приводим к мг, объём (мл) и МЕ к мг НЕ приводим —
    это разные величины, их смешение даёт ложные сравнения.
"""
from __future__ import annotations

import json
import os
import re

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DATA_SOURCE = "antibio-calc/medical_normalizer (dictionary + parsers)"


def _load(name: str) -> dict:
    try:
        with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # словарь — не критичный ресурс: работаем без него
        return {}


DRUG_SYNONYMS: dict[str, str] = _load("drugs.json")
ROUTE_SYNONYMS: dict[str, str] = _load("routes.json")
UNIT_NORMALIZATION: dict[str, str] = _load("units.json")

# Единицы массы, приводимые к мг. мл/МЕ/тыс.МЕ сюда не входят намеренно.
_MASS_TO_MG = {"g": 1000.0, "mg": 1.0, "mcg": 0.001}

_MARKERS = re.compile(r"^[#*]+|[#*]+$")
_SPACES_AROUND_PLUS = re.compile(r"\s*\+\s*")


# ---------------------------------------------------------------- препараты
def normalize_drug(raw: str | None) -> str:
    """Бренд/латиница/опечатка → каноническое МКН. Неизвестное — как есть."""
    if not raw or not raw.strip():
        return ""
    cleaned = _SPACES_AROUND_PLUS.sub(" + ", _MARKERS.sub("", raw.strip())).strip()
    return DRUG_SYNONYMS.get(cleaned.lower(), cleaned)


def normalize_route(raw: str | None) -> str:
    """Путь введения → контролируемый словарь (oral/iv/im/...)."""
    if not raw or not raw.strip():
        return "unknown"
    key = raw.strip().lower()
    if key in ROUTE_SYNONYMS:
        return ROUTE_SYNONYMS[key]
    # «в/в или в/м» — составной путь
    parts = [p.strip() for p in re.split(r"\s*(?:,|\s+или\s+)\s*", key) if p.strip()]
    found = [ROUTE_SYNONYMS[p] for p in parts if p in ROUTE_SYNONYMS]
    if len(found) >= 2:
        return "|".join(dict.fromkeys(found))
    return "unknown"


def normalize_unit(raw: str | None) -> str:
    if not raw or not raw.strip():
        return ""
    key = raw.strip().lower().rstrip(".")
    return UNIT_NORMALIZATION.get(key, key)


def to_mg(value: float, unit: str) -> float | None:
    """Масса → мг. Для мл/МЕ возвращает None (нельзя складывать разные величины)."""
    factor = _MASS_TO_MG.get(normalize_unit(unit))
    return None if factor is None else round(value * factor, 4)


# --------------------------------------------------------------------- доза
_DOSE_RX = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*"
    r"(мг/кг|мкг/кг|мг|мкг|г|мл|ме|тыс\.?\s*ме)(?![а-я])",
    re.I,
)


def parse_dose(text: str) -> dict:
    """Первая доза в тексте: значение, единица, эквивалент в мг, признак мг/кг."""
    m = _DOSE_RX.search(text or "")
    if not m:
        return {"raw": "", "value": None, "unit": "", "mg": None, "per_kg": False}
    raw_unit = m.group(2).lower().replace(".", "").replace(" ", "")
    per_kg = "/кг" in raw_unit
    unit = raw_unit.replace("/кг", "")
    value = float(m.group(1).replace(",", "."))
    return {
        "raw": m.group(0).strip(),
        "value": value,
        "unit": normalize_unit(unit),
        "mg": None if per_kg else to_mg(value, unit),
        "per_kg": per_kg,
    }


# ---------------------------------------------------------------- кратность
_EVERY_N_HOURS = "every_n_hours"
_STATIC = "static"
_TIMES_PER = "times_per"
_EVERY_N_DAYS = "every_n_days"
_WORD_TIMES_PER = "word_times_per"
_WORD_ADV = "word_adv"
_WORD_DOSES = "word_doses"
_TIMES_PER_WEEK = "times_per_week"
_TIMES_PER_MONTH = "times_per_month"
_EVERY_N_WEEKS = "every_n_weeks"

_WORD_TO_NUM = {
    "один": 1.0, "одну": 1.0, "два": 2.0, "две": 2.0, "три": 3.0,
    "четыре": 4.0, "пять": 5.0, "дважды": 2.0, "трижды": 3.0, "четырежды": 4.0,
}
_PERIOD_DIVISOR = {"ден": 1.0, "сут": 1.0, "нед": 7.0, "мес": 30.0}

# (pattern, static_value, tag, is_range) — порядок важен: диапазоны и «каждые
# N дней/недель» проверяются раньше своих скалярных аналогов.
_FREQ_PATTERNS: list[tuple[re.Pattern, float, str, bool]] = [
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*ч"), 0.0, _EVERY_N_HOURS, True),
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*[-\u2013]\s*\d+\s*часа"), 0.0, _EVERY_N_HOURS, True),
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*ч"), 0.0, _EVERY_N_HOURS, False),
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*часа"), 0.0, _EVERY_N_HOURS, False),
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*(?:дней|дня|день|дн|ден|сут)"), 0.0, _EVERY_N_DAYS, False),
    (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*ч"), 0.0, _EVERY_N_HOURS, True),
    (re.compile(r"раз\s+в\s+(\d+)\s*[-\u2013]?\s*(?:\d+)?\s*часа"), 0.0, _EVERY_N_HOURS, True),
    (re.compile(r"q\s*(\d+)\s*h"), 0.0, _EVERY_N_HOURS, False),
    (re.compile(r"q\s*(\d+)\s*hrs?"), 0.0, _EVERY_N_HOURS, False),
    (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*(?:в|за)\s+(?:1\s+)?(?:ден|сут)"), 0.0, _TIMES_PER, True),
    (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*(?:в|за)\s+(?:1\s+)?(?:нед|мес)"), 0.0, _TIMES_PER, True),
    (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*раз(?:а)?\s*/\s*сут"), 0.0, _TIMES_PER, True),
    (re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*р\s*/\s*сут"), 0.0, _TIMES_PER, True),
    (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+(?:1\s+)?ден"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*раз(?:а)?\s+(?:в|за)\s+сут"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*раз(?:а)?\s*/\s*сут"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*р\s*/\s*сут(?:ки)?"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*р\s+в\s+сут"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+нед"), 0.0, _TIMES_PER_WEEK, False),
    (re.compile(r"(\d+)\s*раз(?:а)?\s+в\s+мес"), 0.0, _TIMES_PER_MONTH, False),
    (re.compile(r"1\s*раз(?:а)?\s+в\s+(\d+)\s*(?:дней|дня|день|дн|ден)"), 0.0, _EVERY_N_DAYS, False),
    (re.compile(r"1\s*раз(?:а)?\s+через\s+(\d+)\s*(?:дней|дня|день|дн|ден)"), 0.0, _EVERY_N_DAYS, False),
    (re.compile(r"кажд(?:ые|ый|ую)\s+(\d+)\s*нед"), 0.0, _EVERY_N_WEEKS, False),
    (re.compile(r"интервал\w*\s+(?:в\s+)?(\d+)\s*нед"), 0.0, _EVERY_N_WEEKS, False),
    (re.compile(r"(один|одну|два|две|три|четыре|пять)\s+раз(?:а)?\s+(?:в|за)\s+(ден|сут|нед|мес)"), 0.0, _WORD_TIMES_PER, False),
    (re.compile(r"(дважды|трижды|четырежды)\s+(?:в|за)\s+(ден|сут|нед)"), 0.0, _WORD_ADV, False),
    (re.compile(r"(\d+)\s*(?:times?|x)\s*(?:per|a|/)\s*day"), 0.0, _TIMES_PER, False),
    (re.compile(r"q\s*[0o]\s*d"), 0.5, _STATIC, False),
    (re.compile(r"\b(?:bid|bd|b\.i\.d\.)"), 2.0, _STATIC, False),
    (re.compile(r"\b(?:tid|tds|t\.i\.d\.)"), 3.0, _STATIC, False),
    (re.compile(r"\b(?:qid|q\.i\.d\.)"), 4.0, _STATIC, False),
    (re.compile(r"\b(?:qd|od|s\.i\.d\.)"), 1.0, _STATIC, False),
    (re.compile(r"\b(?:qh|q\.1?h)"), 24.0, _STATIC, False),
    (re.compile(r"(?:в|на|за)\s+(\d+)\s*[-\u2013]\s*\d+\s*(?:прием|введен)"), 0.0, _TIMES_PER, True),
    (re.compile(r"(?:в|на|за)\s+(\d+)\s*(?:прием|введен)"), 0.0, _TIMES_PER, False),
    (re.compile(r"(?:в|на)\s+(один|одну|два|две|три|четыре|пять)\s*(?:прием|введен)"), 0.0, _WORD_DOSES, False),
    (re.compile(r"в\s+сутки\s+в\s+(\d+)\s*прием"), 0.0, _TIMES_PER, False),
    (re.compile(r"за\s+(\d+)\s*введен\w*\s+в\s+сут"), 0.0, _TIMES_PER, False),
    (re.compile(r"разделенн\w*\s+на\s+(\d+)\s*прием"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*прием(?:а|ов)?\s*$"), 0.0, _TIMES_PER, False),
    (re.compile(r"(\d+)\s*раза?\s*$"), 0.0, _TIMES_PER, False),
    (re.compile(r"через\s+день"), 0.5, _STATIC, False),
    (re.compile(r"ежедн"), 1.0, _STATIC, False),
    (re.compile(r"непрерывн|постоян"), 24.0, _STATIC, False),
    (re.compile(r"однократн"), 1.0, _STATIC, False),
    (re.compile(r"двукратн"), 2.0, _STATIC, False),
    (re.compile(r"тр[её]хкратн"), 3.0, _STATIC, False),
    (re.compile(r"капельно"), 1.0, _STATIC, False),
    (re.compile(r"как\s+можно\s+скоре"), 1.0, _STATIC, False),
    (re.compile(r"разов"), 1.0, _STATIC, False),
    (re.compile(r"в\s+сутки"), 1.0, _STATIC, False),
    (re.compile(r"в\s+день"), 1.0, _STATIC, False),
    (re.compile(r"суточн"), 1.0, _STATIC, False),
]


def parse_frequency(text: str) -> dict:
    """Кратность → приёмов в сутки. Диапазон → нижняя граница + is_range."""
    raw = (text or "").strip().lower()
    if not raw:
        return {"raw": "", "per_day": None, "is_range": False}
    for pattern, static_value, tag, is_range in _FREQ_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        if tag == _STATIC:
            return {"raw": m.group(0), "per_day": static_value, "is_range": False}
        if tag == _WORD_TIMES_PER:
            num = _WORD_TO_NUM.get(m.group(1), 1.0)
            return {"raw": m.group(0), "per_day": num / _PERIOD_DIVISOR.get(m.group(2), 1.0),
                    "is_range": False}
        if tag == _WORD_ADV:
            num = _WORD_TO_NUM.get(m.group(1), 1.0)
            return {"raw": m.group(0), "per_day": num / _PERIOD_DIVISOR.get(m.group(2), 1.0),
                    "is_range": False}
        if tag == _WORD_DOSES:
            return {"raw": m.group(0), "per_day": _WORD_TO_NUM.get(m.group(1), 1.0),
                    "is_range": False}
        try:
            num = float(m.group(1))
        except (IndexError, ValueError, TypeError):
            continue
        if num <= 0:
            continue
        per_day = {
            _EVERY_N_HOURS: 24.0 / num,
            _EVERY_N_DAYS: 1.0 / num,
            _EVERY_N_WEEKS: 1.0 / (num * 7.0),
            _TIMES_PER: num,
            _TIMES_PER_WEEK: num / 7.0,
            _TIMES_PER_MONTH: num / 30.0,
        }.get(tag)
        if per_day is None:
            continue
        return {"raw": m.group(0), "per_day": round(per_day, 3), "is_range": is_range}
    return {"raw": "", "per_day": None, "is_range": False}


# --------------------------------------------------------------------- курс
_RANGE_DAYS = re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*(?:дн|сут|день|дня|дней)")
_SINGLE_DAYS = re.compile(r"(\d+)\s*(?:дн(?:ей|я)?|сут(?:ок|ки)?|день)\b")
_RANGE_WEEKS = re.compile(r"(\d+)\s*[-\u2013\u2014]\s*(\d+)\s*нед")
_SINGLE_WEEKS = re.compile(r"(\d+)\s*нед")
_HOURS = re.compile(r"(\d+)\s*час")
_MAX_HOURS = re.compile(r"не\s*более\s*(\d+)\s*час")
_STATIC_SINGLE = re.compile(r"однократн|разов|одн[аа]\s+доз")


def parse_duration(text: str) -> dict:
    """Курс в днях: min/max/recommended. Диапазон → recommended = нижняя граница."""
    raw = (text or "").strip().lower()
    if not raw:
        return {"raw": "", "min_days": None, "max_days": None, "recommended_days": None,
                "is_range": False}
    m = _RANGE_DAYS.search(raw)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return {"raw": m.group(0), "min_days": lo, "max_days": hi, "recommended_days": lo,
                "is_range": True}
    m = _RANGE_WEEKS.search(raw)
    if m:
        lo, hi = int(m.group(1)) * 7, int(m.group(2)) * 7
        return {"raw": m.group(0), "min_days": lo, "max_days": hi, "recommended_days": lo,
                "is_range": True}
    m = _MAX_HOURS.search(raw)
    if m:
        days = round(int(m.group(1)) / 24, 2)
        return {"raw": m.group(0), "min_days": None, "max_days": days,
                "recommended_days": None, "is_range": False}
    m = _SINGLE_DAYS.search(raw)
    if m:
        d = int(m.group(1))
        return {"raw": m.group(0), "min_days": d, "max_days": d, "recommended_days": d,
                "is_range": False}
    m = _SINGLE_WEEKS.search(raw)
    if m:
        d = int(m.group(1)) * 7
        return {"raw": m.group(0), "min_days": d, "max_days": d, "recommended_days": d,
                "is_range": False}
    m = _HOURS.search(raw)
    if m:
        d = round(int(m.group(1)) / 24, 2)
        return {"raw": m.group(0), "min_days": d, "max_days": d, "recommended_days": d,
                "is_range": False}
    if _STATIC_SINGLE.search(raw):
        return {"raw": "однократно", "min_days": 1, "max_days": 1, "recommended_days": 1,
                "is_range": False}
    return {"raw": "", "min_days": None, "max_days": None, "recommended_days": None,
            "is_range": False}


# ------------------------------------------------------------------- схема
_ROUTE_RX = re.compile(
    r"внутрь|перорально|в/в|в/м|внутривенно|внутримышечно|местно|ингаляц|"
    r"закап|в\s+ухо|в\s+нос|назальн|per\s+os|в/венно|капли",
    re.I,
)


def parse_regimen(text: str) -> dict:
    """Схема из свободного текста протокола: препарат, доза, кратность, курс, путь.

    Возвращает только то, что реально написано в тексте. `confidence` — грубая
    эвристика полноты (сколько из 4 ключевых полей найдено), не «медицинская»
    уверенность: она нужна, чтобы отличить «схема разобрана» от «нашлось одно
    слово».
    """
    src = (text or "").strip()
    dose = parse_dose(src)
    freq = parse_frequency(src)
    dur = parse_duration(src)
    route_raw = _ROUTE_RX.search(src)
    drug = ""
    for alias in sorted(DRUG_SYNONYMS, key=len, reverse=True):
        if len(alias) >= 5 and alias in src.lower():
            drug = DRUG_SYNONYMS[alias]
            break

    daily_mg = None
    if dose["mg"] and freq["per_day"]:
        daily_mg = round(dose["mg"] * freq["per_day"], 1)

    found = sum(1 for x in (drug, dose["value"], freq["per_day"], dur["recommended_days"]) if x)
    warnings: list[str] = []
    if dose["per_kg"]:
        warnings.append("Доза указана на кг массы — нужен вес пациента.")
    if freq["is_range"]:
        warnings.append("Кратность задана диапазоном — взята нижняя граница.")
    if dur["is_range"]:
        warnings.append("Курс задан диапазоном — взята нижняя граница.")
    if not drug:
        warnings.append("Препарат не распознан по словарю — проверьте название.")
    if not dose["value"]:
        warnings.append("Доза в тексте не найдена.")

    return {
        "source_text": src[:500],
        "drug": {"normalized": drug, "known": bool(drug)},
        "dose": dose,
        "frequency": freq,
        "duration": dur,
        "route": normalize_route(route_raw.group(0)) if route_raw else "unknown",
        "route_raw": route_raw.group(0) if route_raw else "",
        "daily_mg": daily_mg,
        "confidence": round(found / 4, 2),
        "warnings": warnings,
        "note": "Разбор детерминированный, без LLM. Сверьте с текстом протокола.",
    }
