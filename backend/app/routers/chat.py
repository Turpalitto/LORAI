"""Чат с ассистентом: обычный ответ и SSE-поток."""
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.cache import cache, record_latency
from ..core.config import DISCLAIMER
from ..core.deps import optional_auth, uid
from ..core.privacy import PII_WARNING, has_pii
from ..core.ratelimit import limiter
from ..rag import generator as rag_gen
from ..rag.generator import answer as rag_answer

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    query: str
    k: int = 6
    nosology: str | None = None
    icd10: str | None = None
    session_id: str | None = None


@router.post("/chat")
@limiter.limit("30/minute")
def chat(b: ChatIn, request: Request, user: dict = Depends(optional_auth)):
    if has_pii(b.query):
        return {"warning": PII_WARNING, "answer": None}
    f = {}
    if b.nosology: f["nosology"] = b.nosology
    if b.icd10: f["icd10"] = b.icd10
    t0 = time.monotonic()
    # Кэшируем только запросы без session_id: follow-up зависит от истории
    # диалога, чужой кэш здесь дал бы неверный контекст.
    ckey = f"chat|{b.query}|{b.k}|{f}" if not b.session_id else None
    hit = cache.get(ckey) if ckey else None
    if hit is not None:
        r = {**hit, "cached": True}
    else:
        r = rag_answer(b.query, k=b.k, filters=f or None,
                       session_id=b.session_id, user=uid(user))
        r["disclaimer"] = DISCLAIMER
        r["cached"] = False
        if ckey:
            cache.set(ckey, {k: v for k, v in r.items() if k != "cached"})
    ms = round((time.monotonic() - t0) * 1000, 1)
    record_latency(ms)
    r["latency_ms"] = ms
    return r


# SSE-заголовки: no-cache и отключение буферизации nginx — без второго
# «поток» снова склеивается в один пакет на прод-прокси.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _sse_events(query: str, k: int, session_id: str | None, filters: dict | None = None,
                user: str = "guest"):
    """Ленивый генератор SSE: отдаёт события по мере генерации. Раньше здесь
    стоял list(answer_stream(...)) — весь ответ собирался до старта ответа,
    TTFB равнялся полному времени генерации (фронт «стримил» фейково).
    latency_ms/record_latency считаются от старта до события done."""
    t0 = time.monotonic()
    for e in rag_gen.answer_stream(query, k=k, filters=filters,
                                   session_id=session_id, user=user):
        if e.get("type") == "done":
            ms = round((time.monotonic() - t0) * 1000, 1)
            record_latency(ms)
            e = {**e, "latency_ms": ms, "disclaimer": DISCLAIMER}
        yield _sse(e)


def _chat_stream_response(query: str, k: int, session_id: str | None,
                          filters: dict | None = None,
                          user: str = "guest") -> StreamingResponse:
    """Общий ответ GET/POST /chat/stream: ПДн-гейт проверяется до генерации
    (одно событие done, LLM не вызывается), иначе — ленивый SSE-поток."""
    if has_pii(query):
        def _pii():
            yield _sse({"type": "done", "warning": PII_WARNING, "answer": None})
        return StreamingResponse(_pii(), media_type="text/event-stream",
                                 headers=_SSE_HEADERS)
    return StreamingResponse(_sse_events(query, k, session_id, filters, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/chat/stream")
@limiter.limit("30/minute")
def chat_stream(query: str, request: Request, k: int = 6,
                session_id: str | None = None,
                user: dict = Depends(optional_auth)):
    """GET-вариант (обратная совместимость): вопрос в query string.
    Потоковый /chat (SSE): meta → token* → [corrected] → done. Отказ,
    уточнения и проверка цифр — те же, что в /chat (единый _prepare).
    Предпочтителен POST /chat/stream (см. ниже)."""
    return _chat_stream_response(query, k, session_id, user=uid(user))


@router.post("/chat/stream")
@limiter.limit("30/minute")
def chat_stream_post(b: ChatIn, request: Request, user: dict = Depends(optional_auth)):
    """POST-вариант /chat/stream — предпочтительный: клинический текст уходит
    телом запроса и не оседает в access-логах, истории браузера и прокси
    (в GET он попадал в query string). Формат SSE идентичен GET."""
    f = {}
    if b.nosology: f["nosology"] = b.nosology
    if b.icd10: f["icd10"] = b.icd10
    return _chat_stream_response(b.query, b.k, b.session_id, f or None, uid(user))
