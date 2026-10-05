"""Excellence-2/2.5/3 (web-срез): скорость (кэш, latency) + надёжность
/health + обратная связь и аналитика для админа."""
import time
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _auth(c, email="admin@lorai.local", pw="admin123"):
    return {"Authorization": "Bearer " + c.post(
        "/auth/login", json={"email": email, "password": pw}).json()["token"]}


def test_ttl_cache_unit():
    from app.core.cache import TTLCache
    c = TTLCache(maxsize=2, ttl=0.05)
    assert c.get("a") is None
    c.set("a", [1, 2])
    assert c.get("a") == [1, 2]
    assert c.stats()["hit_rate"] == 0.5
    time.sleep(0.06)
    assert c.get("a") is None  # протухло
    c.set("x", 1); c.set("y", 2); c.set("z", 3)  # eviction
    assert c.stats()["size"] == 2


def test_search_protocol_cache_flag():
    c = _client()
    body = {"q": "уникальный кэш-запрос H66.9 отит part2"}
    r1 = c.post("/search-protocol", json=body).json()
    r2 = c.post("/search-protocol", json=body).json()
    assert r1["cached"] is False and r2["cached"] is True
    assert r1["items"] == r2["items"] and r1["llm_used"] is False


def test_chat_cache_only_without_session():
    c = _client()
    q = "уникальный кэш-чат H66.9 отит диагностика part3"
    r1 = c.post("/chat", json={"query": q}).json()
    r2 = c.post("/chat", json={"query": q}).json()
    assert r1["cached"] is False and r2["cached"] is True
    assert r1["answer"] == r2["answer"]
    assert "latency_ms" in r1 and "session_id" in r1
    # с session_id — никакого кэша (контекст диалога личный)
    s1 = c.post("/chat", json={"query": q, "session_id": "sess-cache-t"}).json()
    s2 = c.post("/chat", json={"query": q, "session_id": "sess-cache-t"}).json()
    assert s1["cached"] is False and s2["cached"] is False


def test_health_detail():
    c = _client()
    h = c.get("/health").json()
    assert h["ok"] is True
    for k in ("db", "documents", "vector_store", "chunks",
              "llm_configured", "llm_mode", "cache", "avg_latency_ms"):
        assert k in h, k
    assert h["documents"] >= 1 and h["chunks"] >= 0


def test_feedback_and_admin_stats():
    c = _client()
    h = _auth(c)
    assert c.post("/feedback", json={"query": "тест-фидбек отит", "vote": 1},
                  headers=h).json()["ok"] is True
    assert c.post("/feedback", json={"query": "x", "vote": 0}, headers=h).status_code == 400
    assert c.post("/feedback", json={"query": "   ", "vote": 1}, headers=h).status_code == 400
    st = c.get("/admin/stats", headers=h).json()
    assert st["documents"] >= 1
    assert st["feedback"]["up"] >= 1
    assert "knowledge_gaps" in st and "cache" in st and "avg_latency_ms" in st
    # врач — не админ
    hd = _auth(c, "doctor@lorai.local", "doctor123")
    assert c.get("/admin/stats", headers=hd).status_code == 403
    assert c.post("/feedback", json={"query": "док-фидбек", "vote": -1},
                  headers=hd).json()["ok"] is True
