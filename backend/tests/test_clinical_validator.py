"""Тесты валидатора схем (PASS/REVIEW/REJECT).

Проверяем то, что может навредить, если сломается:
  * вердикт умеет только понижаться — ни одна проверка не «улучшает» REVIEW до PASS;
  * неполная схема никогда не получает PASS (иначе врач прочитает «проверено»);
  * доза «мг/кг» без веса не превращается в «примерно 70 кг»;
  * потолок дозы, переданный снаружи, действительно срабатывает.

Клинических потолков по препаратам здесь нет намеренно: в LORAI нет
сертифицированной таблицы максимальных доз, и валидатор её не выдумывает.
"""
import pytest


def _parse(text: str) -> dict:
    from app.clinical import parse_regimen

    return parse_regimen(text)


def _validate(text: str, **kw) -> dict:
    from app.clinical import validate_regimen

    return validate_regimen(_parse(text), **kw)


FULL = "Амоксициллин 500 мг внутрь 3 раза в сутки 7 дней"


# ------------------------------------------------------------------ вердикты
def test_complete_regimen_passes():
    v = _validate(FULL)
    assert v["verdict"] == "PASS"
    assert v["reasons"] == []
    assert v["computed"]["single_mg"] == 500.0
    assert v["computed"]["daily_mg"] == 1500.0


def test_unknown_drug_is_rejected():
    """Свободный текст вместо МКН — не рекомендация, даже если доза красивая."""
    v = _validate("Препарат-ХХХ 500 мг внутрь 3 раза в сутки 7 дней")
    assert v["verdict"] == "REJECT"
    assert "drug_unrecognized" in [r["code"] for r in v["reasons"]]


def test_missing_dose_is_rejected():
    v = _validate("Амоксициллин внутрь 3 раза в сутки 7 дней")
    assert v["verdict"] == "REJECT"
    assert "dose_missing" in [r["code"] for r in v["reasons"]]


def test_missing_frequency_and_duration_are_review():
    v = _validate("Амоксициллин 500 мг внутрь")
    assert v["verdict"] == "REVIEW"
    codes = {r["code"] for r in v["reasons"]}
    assert {"frequency_missing", "duration_missing"} <= codes


def test_unknown_route_is_review():
    v = _validate("Амоксициллин 500 мг 3 раза в сутки 7 дней")
    assert v["verdict"] == "REVIEW"
    assert "route_missing" in [r["code"] for r in v["reasons"]]


# ------------------------------------------------------------------ вес и дозы
def test_per_kg_without_weight_is_review_not_guess():
    v = _validate("Цефтриаксон 50 мг/кг в/м 1 раз в сутки 10 дней")
    assert v["verdict"] == "REVIEW"
    assert "weight_required" in [r["code"] for r in v["reasons"]]
    assert v["computed"]["single_mg"] is None


def test_per_kg_with_weight_computes_and_clears_review():
    v = _validate("Цефтриаксон 50 мг/кг в/м 1 раз в сутки 10 дней", weight_kg=20)
    assert v["verdict"] == "PASS", v["reasons"]
    assert v["computed"]["single_mg"] == 1000.0
    assert v["computed"]["daily_mg"] == 1000.0


def test_external_single_ceiling_downgrades_to_review():
    v = _validate("Амоксициллин 500 мг внутрь 3 раза в сутки 7 дней", max_single_mg=250)
    assert v["verdict"] == "REVIEW"
    assert "above_max_single" in [r["code"] for r in v["reasons"]]


def test_external_daily_ceiling_downgrades_to_review():
    v = _validate(FULL, max_daily_mg=1000)
    assert v["verdict"] == "REVIEW"
    assert "above_max_daily" in [r["code"] for r in v["reasons"]]


def test_absurd_single_dose_is_not_passed():
    """9999 мг разово — ошибка разбора; PASS здесь читался бы как «всё верно»."""
    v = _validate("Амоксициллин 9999 мг внутрь 3 раза в сутки 7 дней")
    assert v["verdict"] == "REVIEW"
    assert "implausible_single_dose" in [r["code"] for r in v["reasons"]]


def test_range_is_flagged_even_when_all_fields_present():
    v = _validate("Амоксициллин 500 мг внутрь 2-3 раза в сутки 7-10 дней")
    assert v["verdict"] == "REVIEW"
    assert "range_lower_bound" in [r["code"] for r in v["reasons"]]


def test_non_mass_unit_cannot_be_converted_to_mg():
    v = _validate("Амоксициллин 5 мл внутрь 3 раза в сутки 7 дней")
    assert v["verdict"] == "REVIEW"
    assert "dose_unit_not_mass" in [r["code"] for r in v["reasons"]]
    assert v["computed"]["single_mg"] is None


# ---------------------------------------------------------------- инварианты
@pytest.mark.parametrize("text", [
    FULL,
    "Амоксициллин 500 мг внутрь",
    "Препарат-ХХХ 500 мг внутрь 3 раза в сутки 7 дней",
    "Цефтриаксон 50 мг/кг в/м 1 раз в сутки 10 дней",
    "Амоксициллин 5 мл внутрь 3 раза в сутки 7 дней",
])
def test_verdict_is_the_worst_check_and_never_upgrades(text):
    """Вердикт = самый строгий из проверок; PASS невозможен при любом замечании."""
    from app.clinical.validator import _RANK

    v = _validate(text)
    assert v["verdict"] == max((c["status"] for c in v["checks"]),
                               key=lambda s: _RANK[s])
    assert all(r["status"] != "PASS" for r in v["reasons"])
    if v["reasons"]:
        assert v["verdict"] != "PASS"


def test_policy_text_is_explicit_about_limits():
    v = _validate(FULL)
    assert "только понижать" in v["policy"]
    assert "не заменяет" in v["note"]


# ------------------------------------------------------------------- эндпоинт
def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_endpoint_accepts_text():
    r = _client().post("/regimen/validate", json={"text": FULL})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "PASS"
    assert body["regimen"]["drug"]["normalized"] == "Амоксициллин"
    assert "disclaimer" in body


def test_endpoint_accepts_parsed_regimen_and_weight():
    parsed = _parse("Цефтриаксон 50 мг/кг в/м 1 раз в сутки 10 дней")
    r = _client().post("/regimen/validate", json={"regimen": parsed, "weight_kg": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verdict"] == "PASS"
    assert body["computed"]["single_mg"] == 1000.0


def test_endpoint_rejects_empty_payload():
    r = _client().post("/regimen/validate", json={"text": "   "})
    assert r.status_code == 400
