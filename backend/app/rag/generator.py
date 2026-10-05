from ..knowledge_base.vector_store import VectorStore
from ..knowledge_base import repository as repo
from ..core.config import settings
from .retriever import classify_intent
from .prompt_builder import build_prompt
from .anti_hallucination import should_refuse, check_numbers, REFUSAL
from .clarify import clarifying_question
from .sessions import expand_query, remember, new_session_id
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
    sid = session_id or new_session_id()
    intent = classify_intent(query or "")
    if not (query or "").strip():
        repo.log_query(query or "", intent, True)
        return {"answer": REFUSAL, "refused": True, "intent": intent,
                "top_score": 0.0, "sources": [], "session_id": sid}
    eff = expand_query(query, session_id)
    chunks = vs().search(eff, k=k, filters=filters)
    top = max((c.get("score", 0) for c in chunks), default=0)
    smap = _source_map(chunks)
    if should_refuse(chunks, settings.LLM_THRESHOLD, eff):
        remember(sid, query)
        repo.log_query(query, intent, True)
        return {"answer": REFUSAL, "refused": True, "intent": intent,
                "top_score": top, "sources": chunks,
                "source_map": smap, "session_id": sid}
    # Умные уточняющие вопросы — после гейта отказа, чтобы вне-доменные
    # вопросы по-прежнему получали честный отказ, а не встречный вопрос.
    cq = clarifying_question(query)
    if cq:
        remember(sid, query)
        repo.log_query(query, "needs_clarification", False)
        return {"answer": None, "refused": False, "intent": "needs_clarification",
                "top_score": top, "sources": chunks,
                "source_map": smap, "session_id": sid,
                "needs_clarification": True, "clarifying_question": cq}
    sys, usr = build_prompt(eff, chunks)
    raw = get_client().complete(sys, usr)
    final = check_numbers(raw, chunks)
    remember(sid, query)
    repo.log_query(query, intent, False)
    return {"answer": final, "refused": False, "intent": intent,
            "top_score": top, "sources": chunks,
            "source_map": smap, "doc_count": len(smap), "session_id": sid}
