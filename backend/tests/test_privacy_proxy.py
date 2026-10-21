"""ПДн-фильтр, IP за прокси и дефолты конфигурации (аудит 2026-10-21).

Закрывают H12 (пропуск телефона в формате «8 (912) …» и ФИО с инициалами),
H15 (лимитер видел адрес прокси) и H5 (дефолты расходились с измеренной
конфигурацией).
"""
from types import SimpleNamespace

import pytest


# --------------------------------------------------------------- H12: ПДн
@pytest.mark.parametrize("text,want", [
    ("амоксициллин 8 500 мг 2 раза в день 10 дней", False),
    ("доза 1000 мг в сутки, курс 7 дней", False),
    ("ребёнку 3 года, вес 15 кг, доза 250 мг", False),
    ("шкала 0-10, 5 баллов из 10", False),
    ("8 (912) 345-67-89", True),
    ("+7 912 345 67 89", True),
    ("8-912-345-67-89", True),
    ("Сидоров С.С. жалуется на боль в ухе", True),
    ("пациент Иванов И.И., 45 лет", True),
    ("СНИЛС 123-456-789 00", True),
])
def test_pii_filter(text, want):
    from app.core.privacy import has_pii

    assert has_pii(text) is want, text


# ------------------------------------------------------- H15: IP за прокси
def _req(xff=None, host="10.0.0.2"):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_proxy_headers_ignored_by_default():
    from app.core.config import settings
    from app.core.deps import resolve_client_ip

    old = settings.TRUST_PROXY_HEADERS
    settings.TRUST_PROXY_HEADERS = False
    try:
        assert resolve_client_ip(_req("1.2.3.4")) == "10.0.0.2"
    finally:
        settings.TRUST_PROXY_HEADERS = old


def test_proxy_headers_used_when_trusted():
    """За nginx иначе все врачи делят один ключ лимита 30/мин."""
    from app.core.config import settings
    from app.core.deps import resolve_client_ip

    old = settings.TRUST_PROXY_HEADERS
    settings.TRUST_PROXY_HEADERS = True
    try:
        assert resolve_client_ip(_req("1.2.3.4, 10.0.0.1")) == "1.2.3.4"
        assert resolve_client_ip(_req(None)) == "10.0.0.2"
    finally:
        settings.TRUST_PROXY_HEADERS = old


# ---------------------------------------------------------- H5: дефолты
def test_defaults_match_measured_config():
    """Дефолты не должны расходиться с конфигурацией, на которой мерили."""
    from app.core.config import Settings

    f = Settings.model_fields
    assert f["VECTOR_BACKEND"].default == "embeddings"
    assert f["HYBRID_WEIGHT"].default == 0.15
    assert f["RERANK_BLEND"].default == 0.3
    assert f["SECTION_BOOST"].default == 1.15
