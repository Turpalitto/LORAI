"""Тесты версионирования API: /v1 — канонический путь, старый — совместимость.

Смысл: контракт должен уметь меняться, не ломая уже установленные клиенты.
Поэтому оба пути обязаны отвечать одинаково, а «устаревший» — быть помеченным.
"""
import pytest


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_health_available_on_both_paths():
    c = _client()
    old = c.get("/health")
    new = c.get("/v1/health")
    assert old.status_code == new.status_code == 200
    assert old.json() == new.json()


def test_health_is_not_marked_deprecated():
    """/health — операционный эндпоинт (docker healthcheck), он вне версий."""
    assert "Deprecation" not in _client().get("/health").headers


def test_legacy_path_is_marked_deprecated_with_successor_link():
    c = _client()
    r = c.post("/regimen/validate", json={"text": "Амоксициллин 500 мг внутрь 3 раза в сутки 7 дней"})
    assert r.status_code == 200
    assert r.headers.get("Deprecation") == "true"
    assert '/v1/regimen/validate' in r.headers.get("Link", "")


def test_versioned_path_works_and_is_not_deprecated():
    c = _client()
    r = c.post("/v1/regimen/validate",
               json={"text": "Амоксициллин 500 мг внутрь 3 раза в сутки 7 дней"})
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == "PASS"
    assert "Deprecation" not in r.headers


def test_same_answer_on_both_paths():
    c = _client()
    body = {"weight_kg": 20, "mg_per_kg": 45, "frequency": "2 раза в сутки"}
    old = c.post("/dosage", json=body).json()
    new = c.post("/v1/dosage", json=body).json()
    assert old == new


def test_openapi_exposes_only_versioned_paths():
    """Новый клиент должен видеть только /v1: legacy скрыт из схемы."""
    paths = _client().get("/openapi.json").json()["paths"]
    assert any(p.startswith("/v1/") for p in paths)
    legacy = [p for p in paths if not p.startswith("/v1") and p not in
              {"/health", "/docs", "/redoc", "/openapi.json"}]
    assert legacy == [], legacy


def test_auth_flow_works_under_v1():
    c = _client()
    r = c.post("/v1/auth/login", json={"email": "admin@lorai.local", "password": "admin123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    # защищённый эндпоинт: токен должен приниматься и на версионированном пути
    hist = c.get("/v1/history", headers={"Authorization": f"Bearer {token}"})
    assert hist.status_code == 200, hist.text
    assert "items" in hist.json()
