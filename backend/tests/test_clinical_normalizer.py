"""Тесты клинической нормализации (перенос из antibio-calc) и защитных гейтов.

Проверяем ровно то, что может навредить пациенту, если сломается:
  * бренд → МКН (иначе поиск по «Флемоксину» не находит предостережений);
  * диапазон кратности/курса → нижняя граница (верхняя ведёт к передозу);
  * числа в ответе сверяются как числа, а не как подстроки («5» ≠ «500»);
  * ПДн-фильтр не блокирует обычный клинический вопрос.
"""
import pytest


# --------------------------------------------------------------- препараты
def test_brand_names_map_to_inn():
    from app.clinical import normalize_drug

    assert normalize_drug("Флемоксин солютаб") == "Амоксициллин"
    assert normalize_drug("Сумамед") == "Азитромицин"
    assert normalize_drug("Аугментин") == "Амоксициллин + клавулановая кислота"
    assert normalize_drug("amoxicillin") == "Амоксициллин"


def test_normalize_is_idempotent_and_keeps_unknown():
    from app.clinical import normalize_drug

    once = normalize_drug("Амоксициллин")
    assert normalize_drug(once) == once
    assert normalize_drug("Препарат-ХХХ") == "Препарат-ХХХ"
    assert normalize_drug("") == ""


# --------------------------------------------------------------------- доза
def test_parse_dose_units_and_per_kg():
    from app.clinical import parse_dose

    d = parse_dose("Амоксициллин 500 мг внутрь")
    assert (d["value"], d["unit"], d["mg"], d["per_kg"]) == (500.0, "mg", 500.0, False)

    d = parse_dose("Цефтриаксон 50 мг/кг в/м")
    assert d["per_kg"] is True and d["mg"] is None and d["value"] == 50.0

    # 1 г = 1000 мг; мл к мг не приводим (разные величины)
    assert parse_dose("1 г")["mg"] == 1000.0
    assert parse_dose("5 мл")["mg"] is None


# ---------------------------------------------------------------- кратность
@pytest.mark.parametrize("text,expected", [
    ("3 раза в сутки", 3.0),
    ("2 раза в день", 2.0),
    ("каждые 8 часов", 3.0),
    ("1 раз в день", 1.0),
    ("bid", 2.0),
    ("дважды в день", 2.0),
    ("каждые 12 часов", 2.0),
])
def test_parse_frequency(text, expected):
    from app.clinical import parse_frequency

    assert parse_frequency(text)["per_day"] == expected


def test_frequency_range_takes_lower_bound():
    from app.clinical import parse_frequency

    r = parse_frequency("2-3 раза в сутки")
    assert r["per_day"] == 2.0 and r["is_range"] is True


def test_frequency_unknown_is_none_not_guess():
    from app.clinical import parse_frequency

    r = parse_frequency("по назначению врача")
    assert r["per_day"] is None and r["is_range"] is False


# --------------------------------------------------------------------- курс
def test_parse_duration_range_and_single():
    from app.clinical import parse_duration

    d = parse_duration("5-7 дней")
    assert (d["min_days"], d["max_days"], d["recommended_days"], d["is_range"]) == (5, 7, 5, True)

    d = parse_duration("курс 10 дней")
    assert d["recommended_days"] == 10 and d["is_range"] is False

    d = parse_duration("не более 72 часов")
    assert d["max_days"] == 3.0 and d["recommended_days"] is None


# ------------------------------------------------------------------- схема
def test_parse_regimen_full_sentence():
    from app.clinical import parse_regimen

    r = parse_regimen("Амоксициллин 500 мг внутрь 3 раза в сутки 7 дней.")
    assert r["drug"]["normalized"] == "Амоксициллин"
    assert r["dose"]["value"] == 500.0
    assert r["frequency"]["per_day"] == 3.0
    assert r["duration"]["recommended_days"] == 7
    assert r["route"] == "oral"
    assert r["daily_mg"] == 1500.0
    assert r["confidence"] == 1.0


def test_parse_regimen_per_kg_warns_about_weight():
    from app.clinical import parse_regimen

    r = parse_regimen("Цефтриаксон 50 мг/кг в/м 1 раз в сутки 5-7 дней")
    assert r["dose"]["per_kg"] is True
    assert r["duration"]["is_range"] is True
    assert any("вес" in w for w in r["warnings"])
    assert any("диапазон" in w for w in r["warnings"])


# ------------------------------------------------- защита от выдуманных цифр
def test_check_numbers_catches_order_of_magnitude_error():
    """Регресс: «5 мг» проходило проверку, если в источнике было «500 мг»."""
    from app.rag.anti_hallucination import check_numbers

    chunks = [{"text": "Амоксициллин 500 мг 3 раза в сутки 7 дней."}]
    assert "проверки" in check_numbers("Амоксициллин 5 мг 3 раза в сутки.", chunks)
    assert "проверки" in check_numbers("Амоксициллин 50 мг 3 раза в сутки.", chunks)
    assert "проверки" not in check_numbers("Амоксициллин 500 мг 3 раза в сутки.", chunks)


def test_check_numbers_handles_thousands_separator():
    from app.rag.anti_hallucination import check_numbers

    chunks = [{"text": "Разовая доза 1000 мг."}]
    assert "проверки" not in check_numbers("Разовая доза 1 000 мг.", chunks)


# -------------------------------------------------------------- ПДн-фильтр
def test_pii_filter_does_not_block_clinical_wording():
    from app.main import _has_pii

    assert _has_pii("фамилия врача в протоколе не указана, какой код МКБ у отита?") is False
    assert _has_pii("амоксициллин 875 мг 2 раза в день взрослому") is False


def test_pii_filter_still_catches_real_identifiers():
    from app.main import _has_pii

    assert _has_pii("СНИЛС 123-456-789 00") is True
    assert _has_pii("пациент Иванов Иван, 01.02.1990, полис 1234 5678 9012 3456") is True
    assert _has_pii("тел +7 999 123-45-67") is True


# --------------------------------------------------------------- эндпоинты
def test_regimen_endpoint_and_empty_input():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/regimen/parse", json={"text": "Азитромицин 500 мг 1 раз в день 3 дня"})
    assert r.status_code == 200
    body = r.json()
    assert body["drug"]["normalized"] == "Азитромицин"
    assert body["duration"]["recommended_days"] == 3
    assert body["disclaimer"]

    assert c.post("/regimen/parse", json={"text": "   "}).status_code == 400


def test_dosage_returns_daily_total():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    r = c.post("/dosage", json={"weight_kg": 20, "mg_per_kg": 40,
                                "max_mg": 3000, "frequency": "3 раза в сутки"})
    body = r.json()
    assert body["single_dose_mg"] == 800.0
    assert body["doses_per_day"] == 3.0
    assert body["daily_mg"] == 2400.0


def test_login_throttles_failed_attempts_only():
    """5 промахов → 429, но успешный вход не блокируется (клиника за NAT)."""
    from fastapi.testclient import TestClient

    from app.main import _LOGIN_FAILS, app

    _LOGIN_FAILS.clear()
    c = TestClient(app)
    bad = {"email": "admin@lorai.local", "password": "wrong"}
    codes = [c.post("/auth/login", json=bad).status_code for _ in range(5)]
    assert codes == [401] * 5
    assert c.post("/auth/login", json=bad).status_code == 429

    _LOGIN_FAILS.clear()
    ok = c.post("/auth/login", json={"email": "admin@lorai.local", "password": "admin123"})
    assert ok.status_code == 200 and ok.json()["role"] == "admin"


def test_upload_strips_path_from_filename():
    """Имя вида "../../evil.pdf" не должно уводить запись из data/raw_pdfs."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    tok = c.post("/auth/login", json={"email": "admin@lorai.local",
                                      "password": "admin123"}).json()["token"]
    r = c.post("/admin/upload",
               headers={"Authorization": f"Bearer {tok}"},
               files={"f": ("../../evil.pdf", b"%PDF-1.4\n" + b"0" * 200, "application/pdf")})
    assert r.status_code == 202, r.text
    assert r.json()["title"] == "evil.pdf"
