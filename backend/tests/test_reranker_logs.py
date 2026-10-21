"""Тесты реранкера и формата логов.

Реранкер проверяем без сети и без модели: подменяем `_model` заглушкой.
Важно зафиксировать три свойства, которые легко сломать незаметно:
  * `score` (честный косинус) не подменяется скором реранкера — иначе врёт
    порог отказа;
  * при выключенном/упавшем реранкере порядок остаётся прежним;
  * хвост за пределами top-N не выбрасывается.
"""
import json
import logging
import uuid


# ------------------------------------------------------------------ реранкер
class _StubModel:
    def __init__(self, scores):
        self._scores = scores
        self.calls = 0

    def predict(self, pairs, batch_size=16, show_progress_bar=False):
        self.calls += 1
        return self._scores[:len(pairs)]


def _chunks(n=5):
    return [{"text": f"чанк {i}", "score": 0.9 - i * 0.01, "section": "treatment"}
            for i in range(n)]


def _set_rerank(monkeypatch, backend="cross", blend=0.5, top_n=20):
    from app.rag import reranker

    monkeypatch.setattr(reranker.settings, "RERANK_BACKEND", backend)
    monkeypatch.setattr(reranker.settings, "RERANK_BLEND", blend)
    monkeypatch.setattr(reranker.settings, "RERANK_TOP_N", top_n)
    return reranker


def test_rerank_off_keeps_order_and_truncates(monkeypatch):
    r = _set_rerank(monkeypatch, backend="off")
    chunks = _chunks()
    out = r.rerank("вопрос", chunks, k=3)
    assert [c["text"] for c in out] == [c["text"] for c in chunks[:3]]
    assert "rerank_score" not in out[0]


def test_rerank_reorders_but_keeps_honest_score(monkeypatch):
    r = _set_rerank(monkeypatch, backend="cross", blend=1.0)
    chunks = _chunks()
    # последний кандидат получает максимальный скор кросс-энкодера
    monkeypatch.setattr(r, "_model", _StubModel([0.1, 0.2, 0.3, 0.4, 5.0]))
    out = r.rerank("вопрос", chunks, k=5)
    assert out[0]["text"] == "чанк 4"
    # score остался косинусом из поиска, а не 5.0
    assert out[0]["score"] == chunks[4]["score"]
    assert out[0]["rerank_score"] == 5.0


def test_rerank_tail_is_not_dropped(monkeypatch):
    r = _set_rerank(monkeypatch, backend="cross", blend=1.0, top_n=2)
    chunks = _chunks(5)
    monkeypatch.setattr(r, "_model", _StubModel([1.0, 0.0]))
    out = r.rerank("вопрос", chunks)
    assert len(out) == 5
    assert {c["text"] for c in out} == {c["text"] for c in chunks}


def test_rerank_failure_keeps_order(monkeypatch):
    class Boom:
        def predict(self, *a, **kw):
            raise RuntimeError("OOM")

    r = _set_rerank(monkeypatch, backend="cross")
    chunks = _chunks()
    monkeypatch.setattr(r, "_model", Boom())
    out = r.rerank("вопрос", chunks, k=4)
    assert [c["text"] for c in out] == [c["text"] for c in chunks[:4]]
    assert all("rerank_score" not in c for c in out)


def test_blend_zero_keeps_cosine_order(monkeypatch):
    """Реранкер включён, но вес 0 — порядок задаёт косинус (для отладки)."""
    r = _set_rerank(monkeypatch, backend="cross", blend=0.0)
    chunks = _chunks()
    monkeypatch.setattr(r, "_model", _StubModel([9.0, 0.0, 0.0, 0.0, 0.0]))
    out = r.rerank("вопрос", chunks, k=5)
    assert [c["text"] for c in out] == [c["text"] for c in chunks]


def test_retrieve_asks_for_more_candidates_only_when_enabled(monkeypatch):
    """При включённом реранкере поиск обязан вернуть top-N, иначе реранжировать нечего."""
    from app.rag import retriever

    calls = {}

    class Store:
        def search(self, query, k=6, filters=None, section_boost=None, general_cap=None):
            calls["k"] = k
            return _chunks(3)

    r = _set_rerank(monkeypatch, backend="off")
    retriever.retrieve(Store(), "лечение отита", k=2)
    assert calls["k"] == 2

    _set_rerank(monkeypatch, backend="cross", top_n=20)
    monkeypatch.setattr(r, "_model", _StubModel([0.0, 0.0, 0.0]))
    retriever.retrieve(Store(), "лечение отита", k=2)
    assert calls["k"] == 20


# --------------------------------------------------------------------- логи
def _record(msg="сообщение %s", args=("тест",)):
    rec = logging.LogRecord("lorai", logging.INFO, __file__, 12, msg, args, None)
    return rec


def test_json_log_line_is_parseable_and_correlated():
    from app.core.logging import _JsonFormatter

    rec = _record()
    rec.request_id = "abc123"
    data = json.loads(_JsonFormatter().format(rec))
    assert data["msg"] == "сообщение тест"
    assert data["level"] == "INFO"
    assert data["request_id"] == "abc123"
    assert data["ts"].endswith("Z")


def test_json_log_keeps_extra_fields():
    """extra=user/doc_id не должны теряться — иначе коллектор бесполезен."""
    from app.core.logging import _JsonFormatter

    rec = _record("разбор не удался", args=())
    rec.request_id = "r1"
    rec.user = "doctor@lorai.local"
    rec.document_id = "doc-1"
    data = json.loads(_JsonFormatter().format(rec))
    assert data["user"] == "doctor@lorai.local"
    assert data["document_id"] == "doc-1"


def test_json_log_includes_exception_text():
    from app.core.logging import _JsonFormatter

    try:
        raise ValueError("сломалось")
    except ValueError:
        import sys

        rec = logging.LogRecord("lorai", logging.ERROR, __file__, 1, "ошибка", (), sys.exc_info())
    data = json.loads(_JsonFormatter().format(rec))
    assert "ValueError" in data["exc"]


def test_log_format_switch(monkeypatch):
    from app.core import logging as applog

    monkeypatch.setattr(applog.settings, "LOG_FORMAT", "json")
    name = f"lorai-test-{uuid.uuid4().hex}"
    lg = applog.get_logger(name)
    assert type(lg.handlers[0].formatter).__name__ == "_JsonFormatter"

    monkeypatch.setattr(applog.settings, "LOG_FORMAT", "text")
    name = f"lorai-test-{uuid.uuid4().hex}"
    lg = applog.get_logger(name)
    assert type(lg.handlers[0].formatter).__name__ == "_RequestIdFormatter"


def test_text_log_line_has_request_id():
    from app.core.logging import _RequestIdFormatter, set_request_id, reset_request_id

    token = set_request_id("req-42")
    try:
        line = _RequestIdFormatter("%(levelname)s [req=%(request_id)s] %(message)s").format(_record())
    finally:
        reset_request_id(token)
    assert "[req=req-42]" in line


def test_request_id_sanitizer_blocks_log_injection():
    from app.core.logging import sanitize_request_id

    assert sanitize_request_id("abc-1_2.3") == "abc-1_2.3"
    injected = sanitize_request_id("abc\nFAKE [ERROR] взлом")
    assert "\n" not in injected and injected != "abc\nFAKE [ERROR] взлом"
    assert len(sanitize_request_id("x" * 200)) == 32
