from ..knowledge_base.vector_store import VectorStore
from ..knowledge_base import repository as repo
from ..core.config import settings
from .retriever import classify_intent
from .prompt_builder import build_prompt
from .anti_hallucination import should_refuse, check_numbers, REFUSAL
_vs = None
def vs() -> VectorStore:
    global _vs
    if _vs is None: _vs = VectorStore(settings.CHROMA_DIR)
    return _vs
def answer(query: str, k: int = 6, filters: dict | None = None) -> dict:
    from ..llm_clients.mock import get_client
    intent = classify_intent(query)
    chunks = vs().search(query, k=k, filters=filters)
    top = max((c.get("score", 0) for c in chunks), default=0)
    if should_refuse(chunks, settings.LLM_THRESHOLD, query):
        repo.log_query(query, intent, True)
        return {"answer": REFUSAL, "refused": True, "intent": intent,
                "top_score": top, "sources": chunks}
    sys, usr = build_prompt(query, chunks)
    raw = get_client().complete(sys, usr)
    final = check_numbers(raw, chunks)
    repo.log_query(query, intent, False)
    return {"answer": final, "refused": False, "intent": intent,
            "top_score": top, "sources": chunks}
