"""Настоящий стриминг SSE, POST-вариант /chat/stream и обогащение /favorites.

TestClient.stream для замера TTFB не годится: транспорт starlette 0.46
буферизует тело до конца ответа (_TestClientTransport.handle_request),
поэтому первый чанк приходит уже после завершения генератора. Время
прихода событий меряем ASGI-хуком send — так проверяется реальная
инкрементальная отдача.
"""
import asyncio
import json
import time

from fastapi.testclient import TestClient

import app.rag.generator as gen
from app.main import app


def _client():
    return TestClient(app)


def _auth(c, email="admin@lorai.local", pw="admin123"):
    return {"Authorization": "Bearer " + c.post(
        "/auth/login", json={"email": email, "password": pw}).json()["token"]}


def _events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def _slow_stream(query, k=6, filters=None, session_id=None):
    """meta уходит сразу, token/done — после паузы: эмулирует медленную LLM."""
    yield {"type": "meta", "refused": False, "intent": "test", "sources": [], "session_id": "s"}
    time.sleep(0.6)
    yield {"type": "token", "text": "ответ"}
    yield {"type": "done", "answer": "ответ"}


async def _run_stream_asgi(body: dict) -> tuple[list[float], str]:
    """POST /chat/stream напрямую через ASGI: метки времени каждого тела
    ответа + собранный SSE-текст. receive() ждёт завершения ответа, иначе
    listen_for_disconnect в StreamingResponse отменит поток."""
    payload = json.dumps(body).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/chat/stream",
        "raw_path": b"/chat/stream", "query_string": b"", "root_path": "",
        "client": ("127.0.0.1", 50123), "server": ("testserver", 80),
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode())],
    }
    sent_request = False
    response_done = asyncio.Event()
    stamps: list[float] = []
    chunks: list[bytes] = []

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": payload, "more_body": False}
        await response_done.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.body":
            chunk = message.get("body", b"")
            if chunk:
                stamps.append(time.monotonic())
                chunks.append(chunk)
            if not message.get("more_body", False):
                response_done.set()

    await app(scope, receive, send)
    return stamps, b"".join(chunks).decode()


def test_first_sse_event_before_generation_finishes(monkeypatch):
    """Ключевой регресс: первый чанк (meta) обязан прийти до конца генерации.
    На старом list(answer_stream(...)) TTFB равнялся полному времени ответа."""
    monkeypatch.setattr(gen, "answer_stream", _slow_stream)
    t0 = time.monotonic()
    stamps, text = asyncio.run(_run_stream_asgi({"query": "средний отит"}))
    assert stamps, "не пришло ни одного тела ответа"
    ttfb, total = stamps[0] - t0, stamps[-1] - t0
    assert ttfb < 0.4, f"TTFB {ttfb:.3f}s — ответ буферизуется целиком (list(...))"
    assert total >= 0.6, f"полный ответ {total:.3f}s — короче паузы генерации"
    assert [e["type"] for e in _events(text)] == ["meta", "token", "done"]


def test_post_stream_same_events_as_get():
    """POST /chat/stream отдаёт тот же SSE-контракт, что GET (mock-провайдер)."""
    c = _client()
    q = {"query": "средний отит диагностика лечение"}
    post = _events(c.post("/chat/stream", json=q).text)
    get = _events(c.get("/chat/stream", params=q).text)
    for evts in (post, get):
        kinds = [e["type"] for e in evts]
        assert kinds[0] == "meta" and kinds[-1] == "done" and "token" in kinds
    assert [e["type"] for e in post] == [e["type"] for e in get]
    assert post[-1]["latency_ms"] is not None and "disclaimer" in post[-1]


def test_post_stream_pii_gate_skips_llm(monkeypatch):
    """ПДн в теле POST: одно событие done с предупреждением, LLM не зовём."""
    calls = []

    def _boom(*a, **kw):
        calls.append(1)
        raise AssertionError("при ПДн answer_stream/LLM вызываться не должен")

    monkeypatch.setattr(gen, "answer_stream", _boom)
    c = _client()
    evts = _events(c.post("/chat/stream", json={"query": "СНИЛС 123-456-789 00"}).text)
    assert calls == []
    assert len(evts) == 1 and evts[0]["type"] == "done"
    assert evts[0]["answer"] is None and "персональные данные" in evts[0]["warning"]


def test_favorites_enriched_with_document_metadata():
    """К избранному добавляются nosology/title/icd10_codes из репозитория."""
    from app.knowledge_base import repository as repo

    doc = next(d for d in repo.list_documents() if d["title"].startswith("TEST:"))
    c = _client()
    h = _auth(c)
    assert c.post("/favorites", json={"doc_id": doc["document_id"], "note": "н"},
                  headers=h).json()["ok"] is True
    it = next(x for x in c.get("/favorites", headers=h).json()["items"]
              if x["doc_id"] == doc["document_id"])
    assert it["nosology"] == doc["nosology"] and it["title"] == doc["title"]
    assert it["icd10_codes"] == doc["icd10_codes"]
    assert it["note"] == "н" and "id" in it  # старые поля не тронуты


def test_favorites_missing_document_does_not_fail():
    """Удалённый/неизвестный doc_id: пустые поля вместо 500."""
    c = _client()
    h = _auth(c)
    c.post("/favorites", json={"doc_id": "нет-такого-документа"}, headers=h)
    r = c.get("/favorites", headers=h)
    assert r.status_code == 200
    it = next(x for x in r.json()["items"] if x["doc_id"] == "нет-такого-документа")
    assert it["nosology"] == "" and it["title"] == "" and it["icd10_codes"] == []
