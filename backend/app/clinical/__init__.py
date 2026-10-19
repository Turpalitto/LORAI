"""Клиническая нормализация схем лекарственной терапии.

Перенесено из проекта antibio-calc (`medical_normalizer`) — там этот слой
обкатан на 500+ PDF клинрекомендаций и 726 тестах. В LORAI берём только
детерминированную часть: словари синонимов и разбор дозы/кратности/курса.
LLM не используется, ничего не домысливается: если поле не найдено — оно
остаётся None, а не заполняется «правдоподобным» значением.
"""

from .normalizer import (
    DATA_SOURCE,
    normalize_drug,
    normalize_route,
    normalize_unit,
    parse_dose,
    parse_duration,
    parse_frequency,
    parse_regimen,
)

__all__ = [
    "DATA_SOURCE",
    "normalize_drug",
    "normalize_route",
    "normalize_unit",
    "parse_dose",
    "parse_duration",
    "parse_frequency",
    "parse_regimen",
]
