"""Приватность истории, схема БД и устойчивость индекса.

Проверяем то, что раньше молчало: автор запроса не сохранялся (история была
общей на всю клинику), схема создавалась в обход миграций, а индекс писался
поверх файла без атомарности.
"""
import os


def _token(c, email: str, pw: str) -> dict:
    r = c.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_chat_records_author_and_history_is_scoped():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    admin = _token(c, "admin@lorai.local", "admin123")
    doctor = _token(c, "doctor@lorai.local", "doctor123")

    # разные формулировки — иначе второй запрос попадёт в кэш и не залогируется
    c.post("/chat", json={"query": "острый средний отит: антибиотик выбора"},
           headers=admin)
    c.post("/chat", json={"query": "острый средний отит: отоскопическая картина"},
           headers=doctor)

    own = c.get("/history?limit=50", headers=doctor).json()
    assert own["scope"] == "own"
    assert own["items"], "история врача пуста — автор запроса не записался"
    assert {i["user"] for i in own["items"]} == {"doctor@lorai.local"}
    assert any("отоскопическая" in i["query"] for i in own["items"])
    assert not any("антибиотик выбора" in i["query"] for i in own["items"])

    everything = c.get("/history?limit=50&scope=all", headers=admin).json()
    assert everything["scope"] == "all"
    assert {"admin@lorai.local", "doctor@lorai.local"} <= {i["user"] for i in everything["items"]}

    # врачу общий список закрыт
    assert c.get("/history?scope=all", headers=doctor).status_code == 403


def test_anonymous_chat_is_logged_as_guest():
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    c.post("/chat", json={"query": "средний отит: жалобы и анамнез"})
    items = c.get("/history?limit=100&scope=all",
                  headers=_token(c, "admin@lorai.local", "admin123")).json()["items"]
    assert any(i["user"] == "guest" and "анамнез" in i["query"] for i in items)


def test_ensure_schema_creates_and_is_idempotent(tmp_path, monkeypatch):
    """Схема приводится к head миграциями; повторный запуск не падает."""
    from sqlalchemy import create_engine, inspect

    from app.core import migrations
    from app.core.config import settings

    db = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.delenv("LORAI_TESTING", raising=False)

    assert migrations.ensure_schema() == "alembic upgrade head"
    migrations.ensure_schema()  # второй прогон — no-op, а не «duplicate column»

    tables = set(inspect(create_engine(f"sqlite:///{db}")).get_table_names())
    assert {"documents", "query_log", "favorites", "feedback", "alembic_version"} <= tables
    cols = {c["name"] for c in inspect(create_engine(f"sqlite:///{db}")).get_columns("query_log")}
    assert "user" in cols


def test_vector_store_writes_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("VECTOR_BACKEND", "tfidf")
    from app.knowledge_base.vector_store import VectorStore

    store = VectorStore(str(tmp_path))
    store.add([{"text": "амоксициллин 500 мг 3 раза в сутки", "section": "treatment"}],
              {"title": "проба", "nosology": "отит", "document": "проба", "icd10_codes": "H66"})

    assert os.path.exists(os.path.join(str(tmp_path), "fallback.pkl"))
    assert not list(tmp_path.glob("*.tmp")), "остался временный файл индекса"
    assert store.search("амоксициллин", k=1)


def test_sessions_prune_expired():
    from app.rag import sessions

    sessions._SESSIONS.clear()
    for i in range(sessions._PRUNE_AT + 10):
        sessions._SESSIONS[f"old-{i}"] = {"t": 0, "turns": []}

    sessions._get("fresh")
    assert len(sessions._SESSIONS) <= 2, "просроченные сессии не подчищаются"
    assert "fresh" in sessions._SESSIONS
