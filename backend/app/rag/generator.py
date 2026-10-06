from ..knowledge_base.vector_store import VectorStore
from ..knowledge_base import repository as repo
from ..core.config import settings
from .retriever import classify_intent
from .prompt_builder import build_prompt
from .anti_hallucination import should_refuse, check_numbers, REFUSAL
from .clarify import clarifying_question
from .sessions import expand_query, remember, new_session_id
from ..llm_clients.mock import MockLLMClient
_vs = None
def vs() -> VectorStore:
    global _vs
    if _vs is None: _vs = VectorStore(settings.CHROMA_DIR)
    return _vs


def _source_map(chunks: list[dict]) -> dict:
    """Кросс-документный синтез: какой документ что дал ответу."""
    m: dict[str, dict] = {}
    for c in chunks:
        doc = c.get("document") or c.get("title") or c.get("nosology", "?")
        e = m.setdefault(doc, {"chunks": 0, "sections": set()})
        e["chunks"] += 1
        if c.get("section"):
            e["sections"].add(c["section"])
    return {d: {"chunks": v["chunks"], "sections": sorted(v["sections"])} for d, v in m.items()}


def answer(query: str, k: int = 6, filters: dict | None = None,
           session_id: str | None = None) -> dict:
    from ..llm_clients.mock import get_client
    pre = _prepare(query, k=k, filters=filters, session_id=session_id)
    if pre["kind"] != "ready":
        return pre["result"]
    sys, usr, chunks, smap, top, intent, sid = (pre["sys"], pre["usr"], pre["chunks"],
        pre["smap"], pre["top"], pre["intent"], pre["sid"])
    raw = get_client().complete(sys, usr)
    final = check_numbers(raw, chunks)
    remember(sid, query)
    repo.log_query(query, intent, False)
    return {"answer": final, "refused": False, "intent": intent,
            "top_score": top, "sources": chunks,
            "source_map": smap, "doc_count": len(smap), "session_id": sid}


def _prepare(query: str, k: int = 6, filters: dict | None = None,
             session_id: str | None = None) -> dict:
    """Общая pre-стадия answer/answer_stream: гейт отказа и уточнений.
    kind: refused | clarify | ready. Для ready — всё для генерации."""
    sid = session_id or new_session_id()
    intent = classify_intent(query or "")
    if not (query or "").strip():
        repo.log_query(query or "", intent, True)
        return {"kind": "refused", "result": {
            "answer": REFUSAL, "refused": True, "intent": intent,
            "top_score": 0.0, "sources": [], "session_id": sid}}
    eff = expand_query(query, session_id)
    chunks = vs().search(eff, k=k, filters=filters)
    top = max((c.get("score", 0) for c in chunks), default=0)
    smap = _source_map(chunks)
    if should_refuse(chunks, settings.LLM_THRESHOLD, eff):
        remember(sid, query)
        repo.log_query(query, intent, True)
        return {"kind": "refused", "result": {
            "answer": REFUSAL, "refused": True, "intent": intent,
            "top_score": top, "sources": chunks,
            "source_map": smap, "session_id": sid}}
    cq = clarifying_question(query)
    if cq:
        remember(sid, query)
        repo.log_query(query, "needs_clarification", False)
        return {"kind": "clarify", "result": {
            "answer": None, "refused": False, "intent": "needs_clarification",
            "top_score": top, "sources": chunks,
            "source_map": smap, "session_id": sid,
            "needs_clarification": True, "clarifying_question": cq}}
    sys, usr = build_prompt(eff, chunks)
    return {"kind": "ready", "sys": sys, "usr": usr, "chunks": chunks,
            "smap": smap, "top": top, "intent": intent, "sid": sid}


def answer_stream(query: str, k: int = 6, filters: dict | None = None,
                  session_id: str | None = None):
    """Генератор SSE-событий: meta → token* → [corrected?] → done.
    С живым провайдером токены идут от LLM по мере генерации; с mock —
    нарезка готового ответа (транспортный фолбэк, фронт не меняется).
    check_numbers применяется к полному тексту; при правке цифр фронт
    получает событие corrected и заменяет ответ целиком."""
    from ..llm_clients.mock import get_client
    pre = _prepare(query, k=k, filters=filters, session_id=session_id)
    if pre["kind"] != "ready":
        r = pre["result"]
        yield {"type": "meta", **{key: r.get(key) for key in (
            "refused", "intent", "top_score", "sources", "source_map",
            "session_id", "needs_clarification", "clarifying_question")}}
        if r.get("answer"):
            for piece in _slice(r["answer"]):
                yield {"type": "token", "text": piece}
        yield {"type": "done", "answer": r.get("answer")}
        return
    sys, usr, chunks, smap, top, intent, sid = (pre["sys"], pre["usr"], pre["chunks"],
        pre["smap"], pre["top"], pre["intent"], pre["sid"])
    yield {"type": "meta", "refused": False, "intent": intent, "top_score": top,
           "sources": chunks, "source_map": smap, "doc_count": len(smap),
           "session_id": sid}
    client = get_client()
    live = None if isinstance(client, MockLLMClient) else client.stream
    full = ""
    if live is None:
        full = client.complete(sys, usr)
        for piece in _slice(full):
            yield {"type": "token", "text": piece}
    else:
        for piece in live(sys, usr):
            full += piece
            yield {"type": "token", "text": piece}
    final = check_numbers(full, chunks)
    remember(sid, query)
    repo.log_query(query, intent, False)
    if final != full:
        yield {"type": "corrected", "text": final}
    yield {"type": "done", "answer": final}


def _slice(text: str, words: int = 8):
    parts = text.split(" ")
    for i in range(0, len(parts), words):
        tail = i + words < len(parts)
        yield " ".join(parts[i:i + words]) + (" " if tail else "")
