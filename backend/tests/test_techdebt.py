"""Техдолг аудита: delete_by_document, кэш TF-IDF, пустой запрос."""
import tempfile
from app.knowledge_base.vector_store import VectorStore
from app.rag.generator import answer
from app.rag.anti_hallucination import REFUSAL

def _chunks(n=3):
    return [{"text": f"Острый синусит лечение протокол {i} назальный спрей",
             "section": "treatment", "page_range": [1]} for i in range(n)]

def test_delete_by_document_removes_chunks():
    with tempfile.TemporaryDirectory() as d:
        vs = VectorStore(persist_dir=d)
        vs.add(_chunks(3), {"title": "DOC-A", "nosology": "n", "document": "DOC-A", "icd10_codes": "J01"})
        vs.add(_chunks(2), {"title": "DOC-B", "nosology": "n", "document": "DOC-B", "icd10_codes": "J02"})
        assert len(vs.docs) == 5
        removed = vs.delete_by_document("DOC-A")
        assert removed == 3
        assert all(x.get("document") != "DOC-A" for x in vs.docs)
        # индекс и выдача консистентны после удаления
        res = vs.search("синусит лечение", k=6)
        assert all(r["document"] == "DOC-B" for r in res)

def test_tfidf_cache_consistent_with_rebuild():
    with tempfile.TemporaryDirectory() as d:
        vs = VectorStore(persist_dir=d)
        vs.add(_chunks(4), {"title": "D", "nosology": "n", "document": "D", "icd10_codes": "J01"})
        r1 = vs.search("синусит протокол", k=4)
        r2 = vs.search("синусит протокол", k=4)  # второй проход — из кэша
        assert [x["score"] for x in r1] == [x["score"] for x in r2]
        assert len(vs._toks) == len(vs.docs) == 4

def test_empty_query_refuses_without_boost():
    with tempfile.TemporaryDirectory() as d:
        vs = VectorStore(persist_dir=d)
        vs.add(_chunks(2), {"title": "D", "nosology": "n", "document": "D", "icd10_codes": "J01"})
        res = vs.search("", k=2)
        # пустой запрос больше не бустит все документы на +0.25
        assert all(r["score"] < 0.25 for r in res)
    r = answer("   ")
    assert r["refused"] is True and r["answer"] == REFUSAL and r["sources"] == []
