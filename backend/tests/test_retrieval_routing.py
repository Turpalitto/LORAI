"""Тесты маршрутизации вопроса по разделам протокола и калибровки буста.

Замер на золотом наборе (docs/RETRIEVAL_EVAL.md) показал: без маршрутизации
вопрос «лечение отита» вытаскивал определение и жалобы — нужный протокол, но
не тот кусок текста. Здесь проверяем саму логику, чтобы она не деградировала.
"""
import json
import os

import pytest

from app.knowledge_base.vector_store import VectorStore
from app.rag.retriever import retrieve, section_hint

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "..", "data", "eval", "lor_retrieval_golden.json")


# ---------- классификация вопроса ----------
@pytest.mark.parametrize("q,expected", [
    ("лечение острого среднего отита у ребёнка", ["treatment"]),
    ("какой антибиотик назначить при синусите", ["treatment"]),
    ("показания к тонзиллэктомии", ["treatment"]),
    ("доза амоксициллина в мг/кг", ["treatment"]),
    ("диагностика оталгии, какие симптомы", ["diagnostics"]),
    ("критерии установления диагноза по МКБ", ["diagnostics"]),
    ("определение болезни Меньера", ["definition"]),
    ("этиология и патогенез отосклероза", ["definition"]),
    ("расскажи про ухо", []),
    ("", []),
])
def test_section_hint(q, expected):
    assert section_hint(q) == expected


def test_treatment_has_priority_over_diagnostics():
    """«диагностика и лечение» — вопрос про тактику, лечение важнее."""
    assert section_hint("диагностика и лечение отита") == ["treatment"]


# ---------- интеграция поиска ----------
class _StubStore:
    def __init__(self):
        self.seen_boost = "не вызван"

    def search(self, query, k=6, filters=None, section_boost=None, general_cap=None):
        self.seen_boost = section_boost
        self.seen_cap = general_cap
        return [{"text": "x", "score": 0.5, "section": "treatment"}]


def test_retrieve_passes_section_hint_to_store():
    store = _StubStore()
    retrieve(store, "лечение отита", k=3)
    assert store.seen_boost == ["treatment"]


def test_generic_question_has_no_boost():
    store = _StubStore()
    retrieve(store, "расскажи про ухо")
    assert store.seen_boost == []


TXT = "диагностика и лечение отита: осмотр, антибиотик"


def _two_chunk_store(tmp_path) -> VectorStore:
    """Два чанка с ОДИНАКОВЫМ текстом и разными разделами: сырые скоры равны,
    поэтому порядок определяется только бустом — тест детерминирован."""
    vs = VectorStore(str(tmp_path))
    meta = {"title": "КР", "nosology": "Отит", "document": "КР", "icd10_codes": []}
    vs.add([{"text": TXT, "section": "diagnostics"}], meta)
    vs.add([{"text": TXT, "section": "treatment"}], meta)
    return vs


def test_boost_changes_order_only_when_enabled(tmp_path, monkeypatch):
    vs = _two_chunk_store(tmp_path)
    q = "диагностика и лечение отита"

    monkeypatch.setenv("SECTION_BOOST", "1.0")
    plain = vs.search(q, k=2)
    monkeypatch.setenv("SECTION_BOOST", "1.5")
    boosted = vs.search(q, k=2, section_boost=["treatment"])

    assert plain[0]["section"] == "diagnostics"
    assert plain[0]["score"] == plain[1]["score"], "скоры равны — иначе тест не про буст"
    assert boosted[0]["section"] == "treatment", "буст раздела должен поднять лечение на первое место"


def test_score_stays_honest_when_boosted(tmp_path, monkeypatch):
    """Буст меняет порядок, но не подменяет score: иначе гейт отказа врал бы."""
    vs = _two_chunk_store(tmp_path)
    q = "диагностика и лечение отита"
    monkeypatch.setenv("SECTION_BOOST", "1.0")
    raw = {c["section"]: c["score"] for c in vs.search(q, k=2)}
    monkeypatch.setenv("SECTION_BOOST", "5.0")
    boosted = {c["section"]: c["score"] for c in vs.search(q, k=2, section_boost=["treatment"])}
    assert raw == boosted


# ---------- честный откат бэкенда ----------
def test_embeddings_fallback_is_reported(tmp_path, monkeypatch):
    """Если модель недоступна, стор работает на TF-IDF и говорит об этом."""
    monkeypatch.setenv("VECTOR_BACKEND", "embeddings")
    monkeypatch.setenv("EMBEDDING_MODEL", "нет/такой-модели-точно-не-существует")
    vs = VectorStore(str(tmp_path))
    assert vs.backend == "tfidf"
    assert vs.backend_note
    assert "tfidf" in vs.backend_name().lower()


def test_stats_shape(tmp_path):
    vs = VectorStore(str(tmp_path))
    st = vs.stats()
    assert set(st) >= {"backend", "requested", "chunks", "vectors_indexed", "note"}


# ---------- целостность золотого набора ----------
def test_golden_set_is_wellformed():
    data = json.load(open(GOLDEN, encoding="utf-8"))
    items = data["items"]
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "id должны быть уникальны"
    assert len(items) >= 30, "набор должен быть достаточно большим для замера"
    for i in items:
        assert i["q"].strip()
        if i["kind"] == "in_domain":
            assert i["protocols"], f"{i['id']}: нужен ожидаемый протокол"
            allowed = {"definition", "diagnostics", "treatment", "referral_criteria",
                       "prevention", "complications"}
            assert set(i.get("sections") or []) <= allowed, f"{i['id']}: неизвестный раздел"
            assert i.get("sections"), f"{i['id']}: нужен ожидаемый раздел"
        else:
            assert i["kind"] == "out_of_domain"
            assert i["protocols"] == [], f"{i['id']}: вне-доменный вопрос не должен ждать протокол"
