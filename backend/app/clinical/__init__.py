"""Клиническая нормализация схем лекарственной терапии.

Перенесено из проекта antibio-calc (`medical_normalizer`) — там этот слой
обкатан на 500+ PDF клинрекомендаций и 726 тестах. В LORAI берём только
детерминированную часть: словари синонимов и разбор дозы/кратности/курса.
LLM не используется, ничего не домысливается: если поле не найдено — оно
остаётся None, а не заполняется «правдоподобным» значением.

`validate_regimen` — гейт поверх разбора (PASS/REVIEW/REJECT), по мотивам
`REGIMEN_VALIDATION_GATES.md`: умеет только понижать вердикт.
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
from .validator import PASS, REJECT, REVIEW, validate_regimen

__all__ = [
    "DATA_SOURCE",
    "PASS",
    "REJECT",
    "REVIEW",
    "normalize_drug",
    "normalize_route",
    "normalize_unit",
    "parse_dose",
    "parse_duration",
    "parse_frequency",
    "parse_regimen",
    "validate_regimen",
]
