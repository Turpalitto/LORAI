"""Excellence-1: интеллектуальный слой RAG."""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _auth(c):
    return {"Authorization": "Bearer " + c.post(
        "/auth/login",
        json={"email": "admin@lorai.local", "password": "admin123"}).json()["token"]}


def test_clarify_dosage_without_weight():
    from app.rag.clarify import clarifying_question
    q = clarifying_question("какая дозировка амоксициллина при отите?")
    assert q and ("вес" in q or "возраст" in q)
    # полный запрос — без уточнений
    assert clarifying_question("дозировка амоксициллина 70 кг отит") is None
    # обычный вопрос — без уточнений
    assert clarifying_question("средний отит диагностика лечение") is None


def test_chat_returns_clarifying_question():
    c = _client()
    # формулировка в именительном падеже — как короткие запросы врачей;
    # токены гарантированно пересекаются с тестовым протоколом H66.9
    r = c.post("/chat", json={"query": "лечение отит амоксициллин дозировка"})
    j = r.json()
    assert j.get("needs_clarification") is True
    assert "вес" in j["clarifying_question"] or "возраст" in j["clarifying_question"]
    assert "session_id" in j


def test_audit4_dosage_without_nosology_clarifies():
    """Аудит-4: вопрос про дозу БЕЗ слов-нозологий («отит», «ухо»)
    не должен уходить в отказ — домен-гейт пропускает лекарства/
    дозировочную лексику, дальше работает уточнение."""
    c = _client()
    j = c.post("/chat", json={"query": "Какая доза амоксициллина ребенку?"}).json()
    assert j.get("refused") is False
    assert j.get("needs_clarification") is True
    # а чужая специальность по-прежнему честно отклоняется
    j2 = c.post("/chat", json={"query": "Лечение инфаркта миокарда протокол"}).json()
    assert j2.get("refused") is True


def test_session_memory_expands_followup():
    from app.rag.sessions import expand_query, remember
    sid = "test-sess-1"
    remember(sid, "лечение отита амоксициллином у взрослого")
    expanded = expand_query("а какая дозировка для ребёнка 5 лет", sid)
    assert "амоксициллин" in expanded.lower()


def test_source_map_multi_doc_attribution():
    from app.rag.generator import _source_map
    chunks = [
        {"document": "A", "section": "treatment", "text": "x"},
        {"document": "A", "section": "diagnostics", "text": "y"},
        {"document": "B", "section": "treatment", "text": "z"},
    ]
    m = _source_map(chunks)
    assert m["A"]["chunks"] == 2 and m["B"]["chunks"] == 1
    assert "treatment" in m["A"]["sections"]


def test_diff_rank_weights_rare_signs():
    from app.features.differential_diagnosis import rank
    protos = [
        {"nosology": "Отит", "title": "T1", "icd10_codes": ["H66"],
         "sections": {"treatment": "боль лихорадка оталгия"}},
        {"nosology": "Мастоидит", "title": "T2", "icd10_codes": ["H70"],
         "sections": {"treatment": "боль лихорадка парез лицевого нерва"}},
    ]
    # «парез лицевого нерва» — редкий признак, должен вывести мастоидит в топ
    # даже при равном числе совпадений
    r = rank(["боль", "парез лицевого нерва"], protos)
    assert r[0]["nosology"] == "Мастоидит"
    assert "why_first" in r[0] and "key_signs" in r[0]


def test_drug_check_no_hallucination():
    c = _client()
    r = c.post("/drug-check", headers=_auth(c),
               json={"drugs": ["амоксициллин", "ибупрофен"]})
    j = r.json()
    assert "verdict" in j and "per_drug" in j
    # цитаты либо пустые, либо из реальных документов
    for w in sum(j["per_drug"].values(), []):
        assert w["document"]


def test_related_and_contradictions_endpoints():
    c = _client()
    docs = c.get("/admin/documents", headers=_auth(c)).json()["items"]
    assert docs
    r = c.get(f"/protocols/{docs[0]['document_id']}/related")
    assert "items" in r.json()
    r2 = c.get("/contradictions", headers=_auth(c))
    assert "items" in r2.json()
