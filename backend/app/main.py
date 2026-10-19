from fastapi import (FastAPI, UploadFile, Depends, HTTPException, Header, Request,
                     BackgroundTasks)
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
from .core.logging import (log, get_request_id, reset_request_id,
                           sanitize_request_id, set_request_id)
from .rag import generator as rag_gen
import os, re, tempfile, threading, time, json, uuid

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

# Request-id: один id на запрос, в заголовке ответа и в каждой строке лога.
# Путь логируем без query string — в GET /chat/stream там клинический текст.
@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = sanitize_request_id(request.headers.get("X-Request-ID"))
    token = set_request_id(rid)
    t0 = time.monotonic()
    try:
        response = await call_next(request)
        ms = round((time.monotonic() - t0) * 1000, 1)
        response.headers["X-Request-ID"] = rid
        # Логируем ДО сброса контекста, иначе в строке будет [req=-].
        if request.url.path != "/health":
            log.info("%s %s -> %s %.1fms", request.method, request.url.path,
                     response.status_code, ms)
        return response
    except Exception:
        log.exception("необработанная ошибка: %s %s", request.method, request.url.path)
        raise
    finally:
        reset_request_id(token)


# Необработанное исключение наружу отдаём без трейсбека и текста ошибки:
# раньше FastAPI возвращал "Internal Server Error" без возможности связать
# ответ с записью в логе. В тестах обработчик не ставим — пусть падает
# громко с трейсбеком, иначе отладка превращается в угадывание.
if os.getenv("LORAI_TESTING") != "1":
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("необработанная ошибка: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={
            "detail": "Внутренняя ошибка сервера", "request_id": get_request_id()})

# Учётки живут в таблице `users` (миграция 0004). env используется только для
# первичного сида: раньше USERS собирался из env при каждом старте, поэтому
# добавить врача можно было лишь правкой .env и рестартом, а смена пароля
# откатывалась при следующем деплое.
BOOTSTRAPPED_USERS = repo.DEFAULT_USERS_CREATED

# Политика хранения: тексты клинических запросов и журнал не хранятся вечно.
# В тестах не чистим — БД и так временная, а прогон не должен зависеть от даты.
if os.getenv("LORAI_TESTING") != "1":
    PURGED_ON_START = {
        "queries": repo.purge_old_queries(settings.QUERY_RETENTION_DAYS),
        "audit": repo.purge_old_audit(settings.AUDIT_RETENTION_DAYS),
    }


def auth(authorization: str = Header(default="")) -> dict:
    """Проверка токена + сверка с БД.

    Роль берётся из БД, а не из токена: иначе понижение в правах или
    отключение учётки не действовало бы до истечения токена (8 часов).
    Токен для несуществующего пользователя (например, выданный до переезда
    учёток в БД) пропускается с ролью из токена — иначе все сессии умерли бы
    при деплое.
    """
    if not authorization.startswith("Bearer "): raise HTTPException(401, "Нет токена")
    try: payload = decode_token(authorization[7:])
    except Exception: raise HTTPException(401, "Неверный токен")
    u = repo.get_user(payload.get("sub", ""))
    if u:
        if not u["active"]:
            raise HTTPException(403, "Учётная запись отключена")
        payload["role"] = u["role"]
    return payload


def optional_auth(authorization: str = Header(default="")) -> dict:
    """Мягкая аутентификация для публичных эндпоинтов (/chat, /chat/stream).

    Токен есть — знаем, кто спросил (нужно для истории запросов); нет, битый
    или учётка отключена — работаем как гость, но автора пишем явно.
    """
    if not authorization.startswith("Bearer "): return {}
    try: payload = decode_token(authorization[7:])
    except Exception: return {}
    u = repo.get_user(payload.get("sub", ""))
    if u:
        if not u["active"]:
            return {}
        payload["role"] = u["role"]
    return payload


def _uid(user: dict) -> str:
    return (user or {}).get("sub") or "guest"


def _ip(request: Request) -> str:
    return get_remote_address(request) or ""


def admin_only(user: dict = Depends(auth)) -> dict:
    if user.get("role") != "admin": raise HTTPException(403, "Только админ")
    return user

class Login(BaseModel): email: str; password: str
# Троттлинг входа: считаем только неудачные попытки (см. login()).
_LOGIN_FAILS: dict[str, list[float]] = {}
_LOGIN_WINDOW = 300.0
_LOGIN_MAX_FAILS = 5
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
    # Словесные маркеры. «фамилия» из списка убрана: это обычное слово
    # клинического вопроса («фамилия врача в протоколе», «фамилия не указана»),
    # и такой запрос блокировался целиком, хотя ПДн в нём нет. Фамилия-пример
    # остаётся («Иванов»), остальные форматы ловятся регулярками выше.
    re.compile(r"\bснилс\b|\bполис\b|\bпаспорт\b|\bиванов[ауы]?\b", re.I),
]

def _has_pii(text: str) -> bool:
    return any(rx.search(text or "") for rx in _PII_RX)

@app.get("/health")
def health():
    """Публичная проверка живости: только ok/degraded и версия.

    Раньше этот эндпоинт без авторизации отдавал число документов и чанков,
    режим LLM, содержимое кэша и текст ошибки БД/векторов — то есть карту
    инфраструктуры любому, кто дотянется до порта. Детали переехали в
    /admin/health (под авторизацией).
    """
    ok = True
    try:
        repo.list_documents()
    except Exception:
        ok = False
    try:
        vs()
    except Exception:
        ok = False
    return {"ok": ok, "status": "ok" if ok else "degraded",
            "version": settings.APP_VERSION}


@app.get("/admin/health")
def admin_health(user: dict = Depends(admin_only)):
    """Детальная проверка зависимостей: БД, векторное хранилище, LLM, кэш."""
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
            "version": _s.APP_VERSION,
            "retention": {"query_days": _s.QUERY_RETENTION_DAYS,
                          "audit_days": _s.AUDIT_RETENTION_DAYS},
            "disclaimer": DISCLAIMER}
@app.post("/auth/login")
def login(b: Login, request: Request):
    """Вход с троттлингом неудачных попыток.

    Лимит считается только по ОШИБКАМ: 5 промахов за 5 минут на пару
    (IP, email) → 429. Успешные входы не блокируются, поэтому клиника за одним
    NAT-адресом и прогон тестов не упираются в лимит, а скриптовый перебор
    пароля упирается. Раньше на /auth/login лимита не было вовсе — при том что
    /chat был ограничен 30/мин.
    """
    key = f"{get_remote_address(request)}|{(b.email or '').lower()}"
    now = time.monotonic()
    fails = [t for t in _LOGIN_FAILS.get(key, []) if now - t < _LOGIN_WINDOW]
    if len(fails) >= _LOGIN_MAX_FAILS:
        raise HTTPException(429, "Слишком много неудачных попыток входа, попробуйте позже")
    u = repo.get_user(b.email)
    if not u or not u["active"] or not verify_pw(b.password, u["pw_hash"]):
        fails.append(now)
        _LOGIN_FAILS[key] = fails
        if len(_LOGIN_FAILS) > 1000:  # не даём словарю расти бесконечно
            for k in [k for k, v in _LOGIN_FAILS.items() if not v or now - v[-1] > _LOGIN_WINDOW]:
                _LOGIN_FAILS.pop(k, None)
        repo.audit(b.email, "auth.login_failed", target=b.email, ip=_ip(request))
        raise HTTPException(401, "Неверный логин/пароль")
    _LOGIN_FAILS.pop(key, None)
    repo.touch_login(u["email"])
    repo.audit(u["email"], "auth.login", target=u["email"], ip=_ip(request))
    return {"token": make_token(u["email"], u["role"]), "role": u["role"]}
@app.post("/chat")
@limiter.limit("30/minute")
def chat(b: ChatIn, request: Request, user: dict = Depends(optional_auth)):
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
        r = rag_answer(b.query, k=b.k, filters=f or None, session_id=b.session_id, user=_uid(user))
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

def _sse_events(query: str, k: int, session_id: str | None, filters: dict | None = None,
                user: str = "guest"):
    """Ленивый генератор SSE: отдаёт события по мере генерации. Раньше здесь
    стоял list(answer_stream(...)) — весь ответ собирался до старта ответа,
    TTFB равнялся полному времени генерации (фронт «стримил» фейково).
    latency_ms/record_latency считаются от старта до события done."""
    t0 = time.monotonic()
    for e in rag_gen.answer_stream(query, k=k, filters=filters, session_id=session_id, user=user):
        if e.get("type") == "done":
            ms = round((time.monotonic() - t0) * 1000, 1)
            record_latency(ms)
            e = {**e, "latency_ms": ms, "disclaimer": DISCLAIMER}
        yield _sse(e)

def _chat_stream_response(query: str, k: int, session_id: str | None,
                          filters: dict | None = None, user: str = "guest") -> StreamingResponse:
    """Общий ответ GET/POST /chat/stream: ПДн-гейт проверяется до генерации
    (одно событие done, LLM не вызывается), иначе — ленивый SSE-поток."""
    if _has_pii(query):
        def _pii():
            yield _sse({"type": "done", "warning": _PII_WARNING, "answer": None})
        return StreamingResponse(_pii(), media_type="text/event-stream", headers=_SSE_HEADERS)
    return StreamingResponse(_sse_events(query, k, session_id, filters, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)

@app.get("/chat/stream")
@limiter.limit("30/minute")
def chat_stream(query: str, request: Request, k: int = 6, session_id: str | None = None,
                user: dict = Depends(optional_auth)):
    """GET-вариант (обратная совместимость): вопрос в query string.
    Потоковый /chat (SSE): meta → token* → [corrected] → done. Отказ,
    уточнения и проверка цифр — те же, что в /chat (единый _prepare).
    Предпочтителен POST /chat/stream (см. ниже)."""
    return _chat_stream_response(query, k, session_id, user=_uid(user))

@app.post("/chat/stream")
@limiter.limit("30/minute")
def chat_stream_post(b: ChatIn, request: Request, user: dict = Depends(optional_auth)):
    """POST-вариант /chat/stream — предпочтительный: клинический текст уходит
    телом запроса и не оседает в access-логах, истории браузера и прокси
    (в GET он попадал в query string). Формат SSE идентичен GET."""
    f = {}
    if b.nosology: f["nosology"] = b.nosology
    if b.icd10: f["icd10"] = b.icd10
    return _chat_stream_response(b.query, b.k, b.session_id, f or None, _uid(user))
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
def dosage(b: DoseIn):
    """Разовая доза по весу + суточная, если кратность распознана из строки
    («3 раза в сутки», «каждые 8 часов»). Разбор — детерминированный."""
    from .clinical import parse_frequency
    fq = parse_frequency(b.frequency)
    return {**dose.calc_dose(b.weight_kg, b.mg_per_kg, b.max_mg, b.frequency, fq["per_day"]),
            "frequency_parsed": fq, "disclaimer": DISCLAIMER}
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
# Замки по document_id: две загрузки одного и того же файла (или повторная
# загрузка во время разбора) шли параллельно и перетирали чанки друг друга —
# последняя запись могла остаться с нулём чанков. Разбор одного документа
# сериализуем, разные документы по-прежнему обрабатываются параллельно.
_UPLOAD_LOCKS: dict[str, threading.Lock] = {}
_UPLOAD_LOCKS_GUARD = threading.Lock()


def _doc_lock(document_id: str) -> threading.Lock:
    with _UPLOAD_LOCKS_GUARD:
        return _UPLOAD_LOCKS.setdefault(document_id, threading.Lock())


def _process_upload(blob: bytes, fname: str, document_id: str, actor: str = "",
                    rid: str = "") -> None:
    with _doc_lock(document_id):
        _process_upload_unlocked(blob, fname, document_id, actor, rid)


def _process_upload_unlocked(blob: bytes, fname: str, document_id: str,
                             actor: str = "", rid: str = "") -> None:
    """Фоновая обработка загруженного файла.

    Раньше 70-страничный PDF разбирался прямо в обработчике: воркер занят
    секунды-десятки секунд (с OCR — минуты), клиент всё это время ждёт ответа.
    Теперь запись создаётся сразу со статусом processing, а разбор идёт после
    ответа; админка опрашивает /protocols/{id}.
    """
    from .llm_clients.mock import MockLLMClient
    from .core.logging import log, reset_request_id, set_request_id

    # Фоновая задача выполняется уже после ответа, когда контекст запроса
    # сброшен: без явного id её логи и аудит не связать с загрузкой.
    rid_token = set_request_id(rid) if rid else None
    fd, tmp = tempfile.mkstemp(prefix="lorai_upload_", suffix="_" + fname[:100])
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        try:
            doc = process_pdf(tmp, MockLLMClient(), title=fname, document_id=document_id)
        except Exception as e:
            log.warning("загрузка %s: разбор не удался (%s)", fname, e)
            repo.update_document(document_id, {"status": "failed"})
            repo.audit(actor, "document.failed", target=document_id,
                       detail=f"{fname}: {e}"[:500])
            return
        # старые чанки из векторного индекса удаляем, иначе дедуп в SQLite
        # не спасает от дублей в выдаче (VectorStore.delete_by_document)
        vs().delete_by_document(doc["title"])
        repo.save_document(doc)
        vs().add(doc["_chunks"], {"title": doc["title"], "nosology": doc["nosology"],
            "document": doc["title"], "icd10_codes": ",".join(doc["icd10_codes"])})
        raw_dir = ROOT_DIR / "data" / "raw_pdfs"
        raw_dir.mkdir(parents=True, exist_ok=True)
        if os.getenv("LORAI_TESTING") != "1":
            try: (raw_dir / fname).write_bytes(blob)
            except Exception: pass
        # Инвалидация кэша: ответы /chat и /search-protocol закэшированы по
        # тексту запроса — после загрузки документа они обязаны его учесть.
        cache.clear()
        repo.audit(actor, "document.processed", target=document_id,
                   detail=f"{doc['title']} chunks={len(doc.get('_chunks', []))}")
    finally:
        if rid_token is not None:
            reset_request_id(rid_token)
        try: os.unlink(tmp)
        except OSError: pass


@app.post("/admin/upload")
@app.post("/admin/upload-pdf")
@limiter.limit("10/minute")
def upload(request: Request, background: BackgroundTasks, f: UploadFile,
           user: dict = Depends(admin_only)):
    if user.get("role") != "admin": raise HTTPException(403, "Только админ")
    # Имя файла приходит от клиента и может содержать путь ("../../etc/x.pdf"):
    # раньше оно подставлялось в (raw_dir / filename).write_bytes() как есть —
    # запись за пределы каталога загрузок. Оставляем только базовое имя.
    fname = os.path.basename((f.filename or "").replace("\\", "/")).strip() or "upload.pdf"
    if not fname.lower().endswith((".pdf", ".txt")): raise HTTPException(400, "Только PDF/TXT")
    blob = f.file.read()
    if len(blob) > 50 * 1024 * 1024: raise HTTPException(400, "Файл больше 50 МБ")
    if fname.lower().endswith(".pdf") and not blob[:4] == b"%PDF": raise HTTPException(400, "Не похоже на PDF")
    # Дедупликация: повторная загрузка того же файла обновляет запись, а не
    # плодит дубликаты. Проверка и создание — под замком по имени файла: два
    # одновременных запроса иначе оба не находили существующий документ и
    # создавали два разных id на один файл (проверено, воспроизводилось).
    with _doc_lock("name:" + fname):
        existing = next((d for d in repo.list_documents(include_processing=True)
                         if d.get("source_file") == fname or d.get("title") == fname), None)
        document_id = existing["document_id"] if existing else str(uuid.uuid4())
        if existing:
            repo.update_document(document_id, {"status": "processing"})
        else:
            repo.save_document({
                "document_id": document_id, "title": fname,
                "nosology": os.path.splitext(fname)[0][:200], "icd10_codes": [],
                "approval_year": 2024, "source_file": fname,
                "processing_status": "processing", "sections": {}, "_full_text": "",
                "extraction_confidence": "low", "needs_manual_review": True,
            })
    background.add_task(_process_upload, blob, fname, document_id, _uid(user),
                        get_request_id())
    repo.audit(_uid(user), "document.upload", target=document_id,
               detail=("reupload:" if existing else "new:") + fname, ip=_ip(request))
    return JSONResponse(status_code=202, content={
        "document_id": document_id, "status": "processing", "title": fname,
        "duplicate": bool(existing), "poll": f"/protocols/{document_id}",
    })
@app.get("/admin/documents")
def docs(user: dict = Depends(admin_only)):
    """Все документы, включая те, что ещё разбираются в фоне (status=processing)."""
    return {"items": repo.list_documents(include_processing=True)}
class DocPatch(BaseModel): nosology: str | None = None; icd10_codes: list[str] | None = None; approval_year: int | None = None; needs_review: bool | None = None
@app.patch("/admin/documents/{doc_id}")
def patch_doc(doc_id: str, b: DocPatch, request: Request, user: dict = Depends(admin_only)):
    patch = {k: v for k, v in b.model_dump().items() if v is not None}
    d = repo.update_document(doc_id, patch)
    if not d: raise HTTPException(404, "Не найдено")
    repo.audit(_uid(user), "document.patch", target=doc_id,
               detail="changed=" + ",".join(patch), ip=_ip(request))
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
    """Предупреждения о совместимости строго по текстам протоколов, без домысливания.

    Названия приводятся к МКН по словарю (Флемоксин → Амоксициллин, Сумамед →
    Азитромицин): иначе поиск по бренду не находил предостережений, которые в
    протоколе написаны международным наименованием.
    """
    from .features.drug_interactions import check_combination
    from .clinical import normalize_drug
    mapping = {d: normalize_drug(d) for d in b.drugs}
    canonical = list(dict.fromkeys(v for v in mapping.values() if v))
    res = check_combination(canonical, lambda d: vs().search(d, k=5))
    res["drugs_normalized"] = mapping
    res["disclaimer"] = DISCLAIMER
    return res
@app.get("/history")
def history(limit: int = 20, scope: str = "own", user: dict = Depends(auth)):
    """История запросов. По умолчанию — только свои; `scope=all` — админу.

    До 1.3.1 эндпоинт возвращал запросы всей клиники любому вошедшему: в
    QueryLog не было автора, фильтровать было нечем.
    """
    if scope == "all":
        if user.get("role") != "admin":
            raise HTTPException(403, "Только админ")
        return {"items": repo.get_history(limit), "scope": "all"}
    return {"items": repo.get_history(limit, user=_uid(user)), "scope": "own"}
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


# --- Управление учётками и журнал действий -------------------------------
# До 1.3.2 пользователи задавались только через .env: добавить врача можно
# было правкой файла и рестартом, а «кто загрузил протокол» не знал никто.

class UserIn(BaseModel):
    email: str
    password: str
    role: str = "doctor"
    full_name: str = ""


class UserPatch(BaseModel):
    role: str | None = None
    active: bool | None = None
    password: str | None = None
    full_name: str | None = None


@app.get("/admin/users")
def admin_users(user: dict = Depends(admin_only)):
    """Список учёток. Хеши паролей наружу не отдаются."""
    return {"items": repo.list_users()}


@app.post("/admin/users", status_code=201)
def admin_create_user(b: UserIn, request: Request, user: dict = Depends(admin_only)):
    try:
        created = repo.create_user(b.email, b.password, b.role, b.full_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    repo.audit(_uid(user), "user.create", target=created["email"],
               detail=f"role={created['role']}", ip=_ip(request))
    return created


@app.patch("/admin/users/{email}")
def admin_patch_user(email: str, b: UserPatch, request: Request,
                     user: dict = Depends(admin_only)):
    """Правка учётки: роль, активность, ФИО, пароль.

    Две защиты от самоблокировки клиники: нельзя отключить/понизить себя и
    нельзя оставить систему без активного администратора. Пароль в журнал
    не пишется — только факт смены.
    """
    target = email.strip().lower()
    me = _uid(user).lower()
    if target == me and ((b.role is not None and b.role != "admin") or b.active is False):
        raise HTTPException(400, "Нельзя отключить или понизить собственную учётную запись")
    cur = repo.get_user(target)
    if not cur:
        raise HTTPException(404, "Пользователь не найден")
    loses_admin = (cur["role"] == "admin" and cur["active"]
                   and ((b.role is not None and b.role != "admin") or b.active is False))
    if loses_admin and repo.count_active_admins() <= 1:
        raise HTTPException(400, "Это последний активный администратор")
    try:
        updated = repo.update_user(target, b.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    changed = [k for k, v in b.model_dump().items() if v is not None]
    repo.audit(me, "user.update", target=target, detail="changed=" + ",".join(changed),
               ip=_ip(request))
    return updated


@app.get("/admin/audit")
def admin_audit(limit: int = 100, action: str | None = None,
                actor: str | None = None, user: dict = Depends(admin_only)):
    """Журнал действий: входы, загрузки/правки протоколов, управление учётками."""
    return {"items": repo.list_audit(limit, action, actor)}


@app.post("/admin/maintenance/purge")
def admin_purge(user: dict = Depends(admin_only)):
    """Ручная очистка по политике хранения (та же, что при старте)."""
    q = repo.purge_old_queries(settings.QUERY_RETENTION_DAYS)
    a = repo.purge_old_audit(settings.AUDIT_RETENTION_DAYS)
    repo.audit(_uid(user), "maintenance.purge", target="query_log,audit_log",
               detail=f"queries={q},audit={a}")
    return {"queries_deleted": q, "audit_deleted": a,
            "query_retention_days": settings.QUERY_RETENTION_DAYS,
            "audit_retention_days": settings.AUDIT_RETENTION_DAYS}
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
class RegimenIn(BaseModel): text: str
@app.post("/regimen/parse")
def regimen_parse(b: RegimenIn):
    """Детерминированный разбор схемы из текста протокола: препарат → МКН,
    доза, кратность, курс, путь введения. LLM не вызывается.

    Нужен там, где раньше приходилось читать текст глазами: проверка загруженной
    КР в админке, сверка схемы с чек-листом, подготовка структурированного
    ингеста (`diagnostics.*` сейчас пустые). Диапазоны берутся по нижней
    границе и помечаются флагом is_range — верхняя граница ведёт к передозу.
    """
    from .clinical import parse_regimen
    if not (b.text or "").strip():
        raise HTTPException(400, "Пустой текст")
    return {**parse_regimen(b.text[:5000]), "disclaimer": DISCLAIMER}
