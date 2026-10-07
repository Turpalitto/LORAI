from fastapi import FastAPI, UploadFile, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse, StreamingResponse
from .core.config import settings, DISCLAIMER, ROOT_DIR
from .core.security import make_token, decode_token, hash_pw, verify_pw
from .knowledge_base import repository as repo
from .rag.generator import answer as rag_answer, vs
from .ingestion.pipeline import process_pdf
from .features import dosage_calculator as dose, differential_diagnosis as dd
from .features import checklist_generator as chk, report_templates as tpl, referral_criteria as ref
from .core.cache import cache, record_latency, avg_latency
from .rag import generator as rag_gen
import os, re, tempfile, time, json

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="LORAI — помощник ЛОР-врача")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
@app.exception_handler(RateLimitExceeded)
def _ratelimit(request, exc): return JSONResponse({"detail": "Слишком много запросов, подождите."}, status_code=429)

# CORS: явный allowlist вместо "*". Origin нативных мобильных клиентов
# отсутствует — такие запросы пропускаются браузерной политикой не проверяются,
# поэтому список нужен только для web-клиентов (CORS не авторизация: JWT
# по-прежнему обязателен на каждом защищённом эндпоинте).
ALLOWED_ORIGINS = [o.strip() for o in settings.LORAI_ALLOWED_ORIGINS.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])

USERS = {settings.ADMIN_EMAIL: {"pw": hash_pw(settings.ADMIN_PASSWORD), "role": "admin"}}
# Врачебный аккаунт создаётся только если он явно задан в env/.env: раньше
# doctor@lorai.local/doctor123 существовал всегда — обходной путь мимо админа
# с известным дефолтом. Через settings, чтобы работал и .env-файл.
if settings.LORAI_DOCTOR_EMAIL and settings.LORAI_DOCTOR_PASSWORD:
    USERS[settings.LORAI_DOCTOR_EMAIL] = {
        "pw": hash_pw(settings.LORAI_DOCTOR_PASSWORD), "role": "doctor"}
def auth(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "): raise HTTPException(401, "Нет токена")
    try: return decode_token(authorization[7:])
    except Exception: raise HTTPException(401, "Неверный токен")
def admin_only(user: dict = Depends(auth)) -> dict:
    if user.get("role") != "admin": raise HTTPException(403, "Только админ")
    return user

class Login(BaseModel): email: str; password: str
class ChatIn(BaseModel): query: str; k: int = 6; nosology: str | None = None; icd10: str | None = None; session_id: str | None = None
class DoseIn(BaseModel): weight_kg: float; mg_per_kg: float; max_mg: float | None = None; frequency: str = ""
class DiffIn(BaseModel): symptoms: list[str]
class RefIn(BaseModel): doc_id: str; answers: dict

# ПДн-фильтр входящих запросов: раньше был список из 5 подстрок, который
# пропускал полис ОМС, дату рождения, паспорт-серию без слова «паспорт».
# Форматы: СНИЛС, полис ОМС (16 цифр), дата рождения, телефон РФ, паспорт РФ,
# длинные цифровые ID. Слово «снилс/полис» тоже триггерит независимо от формата.
_PII_RX = [
    re.compile(r"\b\d{3}-\d{3}-\d{3}\s*\d{2}\b"),          # СНИЛС 123-456-789 00
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b"),      # полис ОМС 16 цифр
    re.compile(r"\b\d{2}\.\d{2}\.(19|20)\d{2}\b"),           # дата рождения 01.02.1990
    re.compile(r"(?:\+7|8)[\s\-\(]?\d{3}.*\d{2}.*\d{2}"),   # телефон РФ
    re.compile(r"\b\d{2}\s?\d{2}\s?№?\s?\d{6}\b"),          # паспорт РФ 99 99 №123456
    re.compile(r"\bснилс\b|\bполис\b|\bпаспорт\b|\bфамили[яию]|\bиванов[ауы]?\b", re.I),
]

def _has_pii(text: str) -> bool:
    return any(rx.search(text or "") for rx in _PII_RX)

@app.get("/health")
def health():
    """Детальная проверка зависимостей (Excellence-6): БД, векторное
    хранилище, конфигурация LLM, кэш. Не требует аутентификации."""
    try:
        docs = len(repo.list_documents())
        db_ok: bool | str = True
    except Exception as e:
        docs = -1; db_ok = f"DB error: {e}"
    try:
        v = vs()
        chunks = v.chroma.count() if v.chroma is not None else len(v.docs)
        vec_ok: bool | str = True
    except Exception as e:
        chunks = -1; vec_ok = f"vector error: {e}"
    from .core.config import settings as _s
    llm_configured = _s.LLM_PROVIDER != "mock" and bool(_s.LLM_API_KEY)
    try:
        retrieval = vs().stats()
    except Exception as e:
        retrieval = {"backend": "недоступен", "note": str(e)[:120]}
    return {"ok": db_ok is True and vec_ok is True, "db": db_ok, "documents": docs,
            "vector_store": vec_ok, "chunks": chunks, "retrieval": retrieval,
            "llm_configured": llm_configured,
            "llm_mode": ("api:" + _s.LLM_PROVIDER) if llm_configured else "mock",
            "cache": cache.stats(), "avg_latency_ms": avg_latency(),
            "disclaimer": DISCLAIMER}
@app.post("/auth/login")
def login(b: Login):
    u = USERS.get(b.email)
    if not u or not verify_pw(b.password, u["pw"]): raise HTTPException(401, "Неверный логин/пароль")
    return {"token": make_token(b.email, u["role"]), "role": u["role"]}
@app.post("/chat")
@limiter.limit("30/minute")
def chat(b: ChatIn, request: Request):
    if _has_pii(b.query):
        return {"warning": "Не вводите персональные данные пациента!", "answer": None}
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
        r = rag_answer(b.query, k=b.k, filters=f or None, session_id=b.session_id)
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
_PII_WARNING = "Не вводите персональные данные пациента!"

def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"

def _sse_events(query: str, k: int, session_id: str | None, filters: dict | None = None):
    """Ленивый генератор SSE: отдаёт события по мере генерации. Раньше здесь
    стоял list(answer_stream(...)) — весь ответ собирался до старта ответа,
    TTFB равнялся полному времени генерации (фронт «стримил» фейково).
    latency_ms/record_latency считаются от старта до события done."""
    t0 = time.monotonic()
    for e in rag_gen.answer_stream(query, k=k, filters=filters, session_id=session_id):
        if e.get("type") == "done":
            ms = round((time.monotonic() - t0) * 1000, 1)
            record_latency(ms)
            e = {**e, "latency_ms": ms, "disclaimer": DISCLAIMER}
        yield _sse(e)

def _chat_stream_response(query: str, k: int, session_id: str | None,
                          filters: dict | None = None) -> StreamingResponse:
    """Общий ответ GET/POST /chat/stream: ПДн-гейт проверяется до генерации
    (одно событие done, LLM не вызывается), иначе — ленивый SSE-поток."""
    if _has_pii(query):
        def _pii():
            yield _sse({"type": "done", "warning": _PII_WARNING, "answer": None})
        return StreamingResponse(_pii(), media_type="text/event-stream", headers=_SSE_HEADERS)
    return StreamingResponse(_sse_events(query, k, session_id, filters),
                             media_type="text/event-stream", headers=_SSE_HEADERS)

@app.get("/chat/stream")
@limiter.limit("30/minute")
def chat_stream(query: str, request: Request, k: int = 6, session_id: str | None = None):
    """GET-вариант (обратная совместимость): вопрос в query string.
    Потоковый /chat (SSE): meta → token* → [corrected] → done. Отказ,
    уточнения и проверка цифр — те же, что в /chat (единый _prepare).
    Предпочтителен POST /chat/stream (см. ниже)."""
    return _chat_stream_response(query, k, session_id)

@app.post("/chat/stream")
@limiter.limit("30/minute")
def chat_stream_post(b: ChatIn, request: Request):
    """POST-вариант /chat/stream — предпочтительный: клинический текст уходит
    телом запроса и не оседает в access-логах, истории браузера и прокси
    (в GET он попадал в query string). Формат SSE идентичен GET."""
    f = {}
    if b.nosology: f["nosology"] = b.nosology
    if b.icd10: f["icd10"] = b.icd10
    return _chat_stream_response(b.query, b.k, b.session_id, f or None)
@app.get("/protocols")
def protocols(q: str = ""):
    # пустой запрос = листинг метаданных (дашборд «протоколы базы»);
    # с запросом — поиск как раньше
    items = repo.list_documents() if not q.strip() else repo.search_protocols(q)
    return {"items": items, "disclaimer": DISCLAIMER}
class SearchProtocolIn(BaseModel): q: str = ""; nosology: str | None = None; icd10: str | None = None; symptom: str | None = None
@app.post("/search-protocol")
def search_protocol(b: SearchProtocolIn):
    """Точный поиск напрямую по БД. LLM НЕ вызывается — только детерминированная выдача."""
    q = " ".join(x for x in (b.q, b.nosology, b.icd10, b.symptom) if x)
    ckey = f"sp|{q}"
    hit = cache.get(ckey)
    if hit is not None:
        return {"items": hit, "llm_used": False, "cached": True, "disclaimer": DISCLAIMER}
    items = repo.search_protocols(q)
    cache.set(ckey, items)
    return {"items": items, "llm_used": False, "cached": False, "disclaimer": DISCLAIMER}
@app.get("/protocols/{doc_id}")
def one_protocol(doc_id: str):
    d = repo.get_document(doc_id)
    if not d: raise HTTPException(404, "Не найдено")
    return {**d, "disclaimer": DISCLAIMER}
@app.post("/dosage")
def dosage(b: DoseIn): return {**dose.calc_dose(b.weight_kg, b.mg_per_kg, b.max_mg, b.frequency), "disclaimer": DISCLAIMER}
@app.post("/diff-diagnosis")
def diff(b: DiffIn):
    from .core.red_flags import scan as red_scan
    return {"ranked": dd.rank(b.symptoms, repo.search_protocols(" ".join(b.symptoms)) or
        [{"nosology": d["nosology"], "title": d["title"], "icd10_codes": d["icd10_codes"],
          "sections": (repo.get_document(d["document_id"]) or {}).get("sections", {})} for d in repo.list_documents()]),
        "red_flags": red_scan(" ".join(b.symptoms)),
        "disclaimer": DISCLAIMER}
@app.get("/checklist/{doc_id}")
def checklist(doc_id: str):
    d = repo.get_document(doc_id)
    if not d: raise HTTPException(404, "Нет протокола")
    return {**chk.build_checklist(d), "disclaimer": DISCLAIMER}
@app.get("/templates/{kind}/{doc_id}")
def template(kind: str, doc_id: str):
    d = repo.get_document(doc_id) or {"nosology": "", "icd10_codes": [], "title": "", "approval_year": ""}
    return {"text": tpl.render(kind, d), "disclaimer": DISCLAIMER}
@app.post("/referral-check")
def referral(b: RefIn):
    d = repo.get_document(b.doc_id) or {}
    return {**ref.check_referral(b.answers, d), "disclaimer": DISCLAIMER}
@app.post("/admin/upload")
@app.post("/admin/upload-pdf")
@limiter.limit("10/minute")
def upload(request: Request, f: UploadFile, user: dict = Depends(admin_only)):
    if user.get("role") != "admin": raise HTTPException(403, "Только админ")
    if not f.filename.lower().endswith((".pdf", ".txt")): raise HTTPException(400, "Только PDF/TXT")
    blob = f.file.read()
    if len(blob) > 50 * 1024 * 1024: raise HTTPException(400, "Файл больше 50 МБ")
    if f.filename.lower().endswith(".pdf") and not blob[:4] == b"%PDF": raise HTTPException(400, "Не похоже на PDF")
    # Дедупликация: повторная загрузка того же файла обновляет запись, а не плодит дубликаты
    existing = next((d for d in repo.list_documents()
                     if d.get("source_file") == f.filename or d.get("title") == f.filename), None)
    # Именованный temp с гарантированным удалением: раньше tempfile.mktemp
    # оставлял файл навсегда (leak в системном tmp) и имел race-condition.
    fd, tmp = tempfile.mkstemp(prefix="lorai_upload_", suffix="_" + (f.filename or "pdf")[:100])
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        from .llm_clients.mock import MockLLMClient
        try:
            doc = process_pdf(tmp, MockLLMClient(), title=f.filename)
        except Exception as e:
            raise HTTPException(400, f"Не удалось обработать файл: {e}")
    finally:
        try: os.unlink(tmp)
        except OSError: pass
    if existing:
        doc["document_id"] = existing["document_id"]
        # старые чанки из векторного индекса удаляем, иначе дедуп в SQLite
        # не спасает от дублей в выдаче (VectorStore.delete_by_document)
        vs().delete_by_document(doc["title"])
    repo.save_document(doc)
    vs().add(doc["_chunks"], {"title": doc["title"], "nosology": doc["nosology"],
        "document": doc["title"], "icd10_codes": ",".join(doc["icd10_codes"])})
    raw_dir = ROOT_DIR / "data" / "raw_pdfs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    if os.getenv("LORAI_TESTING") != "1":
        try: (raw_dir / f.filename).write_bytes(blob)
        except Exception: pass
    # Инвалидация кэша: ответы /chat и /search-protocol закэшированы по тексту
    # запроса — после загрузки нового документа они обязаны учесть его, иначе
    # врач получает «не найдено» для свежезагруженного протокола до конца TTL.
    cache.clear()
    return {"document_id": doc["document_id"], "nosology": doc["nosology"],
            "title": doc["title"], "icd10": doc["icd10_codes"],
            "processing_status": doc.get("processing_status", "processed"),
            "confidence": doc["extraction_confidence"], "needs_review": doc["needs_manual_review"],
            "duplicate": bool(existing)}
@app.get("/admin/documents")
def docs(user: dict = Depends(admin_only)): return {"items": repo.list_documents()}
class DocPatch(BaseModel): nosology: str | None = None; icd10_codes: list[str] | None = None; approval_year: int | None = None; needs_review: bool | None = None
@app.patch("/admin/documents/{doc_id}")
def patch_doc(doc_id: str, b: DocPatch, user: dict = Depends(admin_only)):
    d = repo.update_document(doc_id, {k: v for k, v in b.model_dump().items() if v is not None})
    if not d: raise HTTPException(404, "Не найдено")
    return d
@app.get("/protocols/{doc_id}/related")
def related(doc_id: str):
    """Похожие протоколы по графу связей нозологий (Excellence-1)."""
    from .features.nosology_graph import related_protocols
    return {"items": related_protocols(doc_id), "disclaimer": DISCLAIMER}
@app.get("/contradictions")
def contradictions(user: dict = Depends(auth)):
    """Пары протоколов с пересекающимися МКБ и расходящимися назначениями."""
    from .features.nosology_graph import find_contradictions
    return {"items": find_contradictions(), "disclaimer": DISCLAIMER}
class DrugCheckIn(BaseModel): drugs: list[str]
@app.post("/drug-check")
def drug_check(b: DrugCheckIn, user: dict = Depends(auth)):
    """Предупреждения о совместимости строго по текстам протоколов, без домысливания."""
    from .features.drug_interactions import check_combination
    res = check_combination(b.drugs, lambda d: vs().search(d, k=5))
    res["disclaimer"] = DISCLAIMER
    return res
@app.get("/history")
def history(limit: int = 20, user: dict = Depends(auth)):
    return {"items": repo.get_history(limit)}
class FeedbackIn(BaseModel): query: str; vote: int; comment: str = ""
@app.post("/feedback")
def feedback(b: FeedbackIn, user: dict = Depends(auth)):
    """Оценка ответа 👍/👎 (Excellence-4: только сбор данных для анализа)."""
    if b.vote not in (1, -1): raise HTTPException(400, "vote должен быть 1 или -1")
    if not b.query.strip(): raise HTTPException(400, "Пустой query")
    return repo.add_feedback(user.get("sub", "doctor"), b.query, b.vote, b.comment)
@app.get("/admin/stats")
def admin_stats(user: dict = Depends(admin_only)):
    """Дашборд использования для администратора клиники (Excellence-4)."""
    s = repo.usage_stats()
    s["cache"] = cache.stats()
    s["avg_latency_ms"] = avg_latency()
    return s
class FavIn(BaseModel): doc_id: str; note: str = ""
@app.post("/favorites")
def add_fav(b: FavIn, user: dict = Depends(auth)):
    return repo.add_favorite(user.get("sub", "doctor"), b.doc_id, b.note)
@app.get("/favorites")
def list_fav(user: dict = Depends(auth)):
    """Избранное врача. К doc_id добавляем человекочитаемые поля протокола
    (nosology/title/icd10_codes), иначе UI показывает только непрозрачный id.
    Отсутствующий/удалённый протокол не роняет эндпоинт — поля остаются
    пустыми."""
    items = repo.list_favorites(user.get("sub", "doctor"))
    try:
        docs = {d["document_id"]: d for d in repo.list_documents()}
    except Exception:
        docs = {}
    for it in items:
        d = docs.get(it.get("doc_id")) or {}
        it["nosology"] = d.get("nosology", "")
        it["title"] = d.get("title", "")
        it["icd10_codes"] = d.get("icd10_codes", [])
    return {"items": items}
@app.delete("/favorites/{fav_id}")
def del_fav(fav_id: int, user: dict = Depends(auth)):
    if not repo.remove_favorite(user.get("sub", "doctor"), fav_id):
        raise HTTPException(404, "Не найдено")
    return {"ok": True}
class RedFlagsIn(BaseModel): text: str = ""
@app.post("/red-flags")
def red_flags(b: RedFlagsIn):
    """Скрининг тревожных симптомов (Excellence-5): статичная таблица,
    LLM не используется. Не диагноз — повод срочно к врачу."""
    from .core.red_flags import scan as red_scan
    return {"flags": red_scan(b.text), "disclaimer": DISCLAIMER}
class CentorIn(BaseModel): fever: bool = False; exudate: bool = False; nodes: bool = False; no_cough: bool = False; age_band: str = "15-44"
class PtaIn(BaseModel): thresholds_db: list[float]
@app.post("/calculators/centor")
def calc_centor(b: CentorIn):
    """Шкала Centor/McIsaac (фарингит): чистая формула, без LLM."""
    from .core import calculators as calc
    try:
        return {**calc.centor(b.fever, b.exudate, b.nodes, b.no_cough, b.age_band), "disclaimer": DISCLAIMER}
    except ValueError as e:
        raise HTTPException(400, str(e))
@app.post("/calculators/pta")
def calc_pta(b: PtaIn):
    """Средний порог слуха PTA и степень потери (ВОЗ): чистая формула."""
    from .core import calculators as calc
    try:
        return {**calc.pta(b.thresholds_db), "disclaimer": DISCLAIMER}
    except ValueError as e:
        raise HTTPException(400, str(e))
