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
