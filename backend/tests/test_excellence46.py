"""Excellence-4/5/6 (web-срез): избранное врача, красные флаги,
клинические калькуляторы. Всё детерминировано, без LLM."""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _auth(c, email="admin@lorai.local", pw="admin123"):
    return {"Authorization": "Bearer " + c.post(
        "/auth/login", json={"email": email, "password": pw}).json()["token"]}


def test_red_flags_hit_and_miss():
    from app.core.red_flags import scan
    hit = scan("у пациента стридор и шумное дыхание")
    assert any(f["id"] == "stridor" for f in hit) and hit[0]["action"]
    assert scan("обычный насморк без температуры") == []


def test_red_flags_endpoint():
    c = _client()
    r = c.post("/red-flags", json={"text": "тризм, не открывает рот"}).json()
    assert any(f["id"] == "trismus" for f in r["flags"])
    assert "disclaimer" in r
    assert c.post("/red-flags", json={"text": "насморк"}).json()["flags"] == []


def test_centor_boundaries():
    from app.core import calculators as calc
    hi = calc.centor(True, True, True, True, "3-14")
    assert hi["score"] == 5 and "Высокая" in hi["interpretation"]
    lo = calc.centor(False, False, False, False, "45+")
    assert lo["score"] == 0 and "Низкая" in lo["interpretation"]
    mid = calc.centor(True, True, False, False, "15-44")
    assert mid["score"] == 2 and "Промежуточная" in mid["interpretation"]
    try:
        calc.centor(False, False, False, False, "99")
        raise AssertionError("должен упасть")
    except ValueError:
        pass


def test_pta_grades_and_validation():
    from app.core import calculators as calc
    assert calc.pta([20, 20, 25, 15])["grade"] == "Норма"
    assert calc.pta([50, 55, 60, 55])["grade"] == "Умеренная потеря слуха"
    assert calc.pta([90, 95, 100, 90])["grade"] == "Глубокая потеря слуха"
    for bad in ([20, 30, 40], [20, 30, 40, 200]):
        try:
            calc.pta(bad)
            raise AssertionError(f"должен упасть: {bad}")
        except ValueError:
            pass


def test_calculator_endpoints_and_400():
    c = _client()
    r = c.post("/calculators/centor", json={
        "fever": True, "exudate": True, "nodes": False,
        "no_cough": False, "age_band": "15-44"}).json()
    assert r["score"] == 2 and "disclaimer" in r
    assert c.post("/calculators/centor", json={"age_band": "99"}).status_code == 400
    p = c.post("/calculators/pta", json={"thresholds_db": [20, 20, 25, 15]}).json()
    assert p["average_db"] == 20.0 and p["grade"] == "Норма"
    assert c.post("/calculators/pta", json={"thresholds_db": [1, 2]}).status_code == 400


def test_favorites_roundtrip_and_isolation():
    from app.knowledge_base import repository as repo
    me, other = "fav-doc-t", "fav-doc-other"
    f = repo.add_favorite(me, "doc-x", "посмотреть")
    assert f["ok"] and repo.list_favorites(other) == []
    mine = repo.list_favorites(me)
    assert any(x["doc_id"] == "doc-x" for x in mine)
    assert repo.remove_favorite(other, f["id"]) is False  # чужую — нельзя
    assert repo.remove_favorite(me, f["id"]) is True
    assert all(x["doc_id"] != "doc-x" for x in repo.list_favorites(me))


def test_favorites_endpoints():
    c = _client()
    h = _auth(c)
    a = c.post("/favorites", json={"doc_id": "doc-ep", "note": "n"}, headers=h).json()
    assert a["ok"] is True
    items = c.get("/favorites", headers=h).json()["items"]
    assert any(i["doc_id"] == "doc-ep" for i in items)
    fid = next(i["id"] for i in items if i["doc_id"] == "doc-ep")
    assert c.delete(f"/favorites/{fid}", headers=h).json() == {"ok": True}
    assert c.delete(f"/favorites/{fid}", headers=h).status_code == 404
    assert c.get("/favorites").status_code == 401  # без токена нельзя


def test_diff_diagnosis_has_red_flags():
    c = _client()
    r = c.post("/diff-diagnosis", json={"symptoms": ["стридор", "одышка"]}).json()
    assert any(f["id"] == "stridor" for f in r["red_flags"])
    r2 = c.post("/diff-diagnosis", json={"symptoms": ["насморк"]}).json()
    assert r2["red_flags"] == [] and "ranked" in r2


def test_diff_rank_token_match_phrase_not_verbatim():
    """Фраза symptom'а не обязана быть дословно в тексте: хватило слов."""
    from app.features import differential_diagnosis as dd
    pros = [
        {"nosology": "Паратонзиллярный абсцесс", "title": "Паратонзиллярный абсцесс",
         "icd10_codes": ["J36"],
         "sections": {"Клиника": "Тризм жевательной мускулатуры, боль в горле"}},
        {"nosology": "Ринит", "title": "Ринит", "icd10_codes": ["J30"],
         "sections": {"Клиника": "Заложенность носа, чихание"}},
    ]
    r = dd.rank(["тризм жевательных мышц", "боль при глотании"], pros)
    assert r and r[0]["nosology"] == "Паратонзиллярный абсцесс"
    assert "why_first" in r[0]


def test_vector_backend_switch(tmp_path, monkeypatch):
    """VECTOR_BACKEND=chroma включает Chroma, default — TF-IDF."""
    import os
    from app.knowledge_base import vector_store as vsm
    monkeypatch.setenv("VECTOR_BACKEND", "chroma")
    vs = vsm.VectorStore(persist_dir=str(tmp_path / "c1"))
    assert vs.chroma is not None
    vs.add([{"text": "Тризм жевательной мускулатуры при абсцессе", "section": "Клиника"}],
           {"title": "Паратонзиллярный абсцесс", "document": "Паратонзиллярный абсцесс",
            "nosology": "Паратонзиллярный абсцесс", "icd10_codes": "J36"})
    r = vs.search("тризм", k=1)
    assert r and "Паратонзиллярный" in r[0].get("document", "")
    monkeypatch.delenv("VECTOR_BACKEND")
    vs2 = vsm.VectorStore(persist_dir=str(tmp_path / "c2"))
    assert vs2.chroma is None
