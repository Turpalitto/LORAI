"""Изоляция тестов от прод-данных.

Устанавливает env ДО импорта app-модулей: SQLite и векторное
хранилище уходят во временную папку, сырые аплоады не persist'ятся
(см. LORAI_TESTING в main.upload). Раньше каждый прогон pytest
писал мусор (broken.pdf, dedup_audit_*.txt) в боевые lorai.db
и data/vector_store/fallback.pkl.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="lorai_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CHROMA_DIR"] = os.path.join(_tmp, "vector_store")
os.environ["LORAI_TESTING"] = "1"

import pytest


@pytest.fixture(scope="session", autouse=True)
def _seed_minimal_docs():
    """Детерминированный сид для изолированной тестовой БД.

    Раньше тесты неявно зависели от прод-данных (test_search_protocol
    падал на пустой БД). Один синтетический протокол H66.9 покрывает
    поиск по МКБ и PATCH-тест без привязки к реальным КР.
    """
    import uuid

    from app.knowledge_base import repository as repo

    text = (
        "Определение\nОстрое воспаление среднего уха H66.9.\nДиагностика\n"
        "Жалобы: оталгия, лихорадка. Отоскопия.\nЛечение\n"
        "Амоксициллин 500 мг 3 раза в сутки 7 дней."
    )
    repo.save_document(
        {
            "document_id": str(uuid.uuid4()),
            "title": "TEST: Острый средний отит",
            "nosology": "Острый средний отит",
            "icd10_codes": ["H66.9"],
            "approval_year": 2024,
            "revision_year": None,
            "source_file": "test-fixture",
            "processing_status": "processed",
            "sections": {"definition": text},
            "extraction_confidence": "medium",
            "needs_manual_review": False,
            "_full_text": text,
        }
    )
