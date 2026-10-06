import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
def test_icd():
    from app.ingestion.icd10_extractor import extract_icd10
    assert "H66.9" in extract_icd10("Диагноз H66.9 острый отит")
    assert "J01.0" in extract_icd10("J01.0 гайморит")
def test_pipeline_synthetic(tmp_path):
    from app.ingestion.pipeline import process_pdf
    f = tmp_path / "test.txt"
    f.write_text("Определение\nОстрый средний отит H66.9\nДиагностика\nОтоскопия\nЛечение\nАмоксициллин 500 мг", encoding="utf-8")
    doc = process_pdf(str(f), title="Острый средний отит")
    assert "H66.9" in doc["icd10_codes"]
    assert len(doc["_chunks"]) > 0
def test_rag_refusal():
    from app.rag.anti_hallucination import should_refuse
    assert should_refuse([], 0.12) is True
    assert should_refuse([{"score": 0.9}], 0.12) is False
    assert should_refuse([{"score": 0.05}], 0.12) is True
def test_api_health():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.get("/health").json()["ok"] is True
def test_chat_grounded():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.post("/chat", json={"query": "средний отит диагностика лечение"})
    assert "disclaimer" in r.json()
def test_chat_stream_sse():
    import json as _json
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/chat/stream", params={"query": "средний отит диагностика лечение"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evts = [_json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    kinds = [e.get("type") for e in evts]
    assert kinds[0] == "meta" and kinds[-1] == "done"
    assert any(k == "token" for k in kinds)
    body = "".join(e.get("text", "") for e in evts if e.get("type") == "token")
    assert len(body) > 0
    assert evts[-1].get("latency_ms") is not None
def test_chat_stream_pii_refused():
    import json as _json
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/chat/stream", params={"query": "Иванов 79001234567"})
    evts = [_json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert evts[-1]["type"] == "done" and evts[-1].get("answer") is None
def test_answer_stream_matches_answer():
    """answer_stream (mock) в сборке даёт тот же ответ, что answer():
    контракт SSE-слоя — фронт не зависит от провайдера."""
    from app.rag.generator import answer, answer_stream
    q = "средний отит диагностика лечение"
    full = answer(q)
    evts = list(answer_stream(q))
    assert evts[0]["type"] == "meta" and evts[-1]["type"] == "done"
    acc = ""
    for e in evts:
        if e["type"] == "token":
            acc += e.get("text", "")
        elif e["type"] == "corrected":
            acc = e["text"]
    assert acc == full["answer"] and evts[-1]["answer"] == full["answer"]
