from fastapi import FastAPI, UploadFile, Depends, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from .core.config import settings, DISCLAIMER, ROOT_DIR
from .core.security import make_token, decode_token, hash_pw, verify_pw
from .knowledge_base import repository as repo
from .rag.generator import answer as rag_answer, vs
from .ingestion.pipeline import process_pdf
from .features import dosage_calculator as dose, differential_diagnosis as dd
from .features import checklist_generator as chk, report_templates as tpl, referral_criteria as ref
from .core.cache import cache, record_latency, avg_latency
import os, tempfile, time

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="LORAI — помощник ЛОР-врача")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
@app.exception_handler(RateLimitExceeded)
def _ratelimit(request, exc): return JSONResponse({"detail": "Слишком много запросов, подождите."}, status_code=429)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

USERS = {settings.ADMIN_EMAIL: {"pw": hash_pw(settings.ADMIN_PASSWORD), "role": "admin"},
         "doctor@lorai.local": {"pw": hash_pw("doctor123"), "role": "doctor"}}
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
    llm_configured = bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))
    return {"ok": db_ok is True and vec_ok is True, "db": db_ok, "documents": docs,
            "vector_store": vec_ok, "chunks": chunks,
            "llm_configured": llm_configured, "llm_mode": "api" if llm_configured else "mock",
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
    if any(p in b.query.lower() for p in ("иванова", "паспорт", "снils", "снилс", "+7")):
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
@app.get("/protocols")
def protocols(q: str = ""): return {"items": repo.search_protocols(q), "disclaimer": DISCLAIMER}
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
    tmp = tempfile.mktemp(suffix="_" + f.filename)
    open(tmp, "wb").write(blob)
    from .llm_clients.mock import MockLLMClient
    try:
        doc = process_pdf(tmp, MockLLMClient(), title=f.filename)
    except Exception as e:
        raise HTTPException(400, f"Не удалось обработать файл: {e}")
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
        try: (raw_dir / f.filename).write_bytes(open(tmp, "rb").read())
        except Exception: pass
    return {"document_id": doc["document_id"], "icd10": doc["icd10_codes"],
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
    return {"items": repo.list_favorites(user.get("sub", "doctor"))}
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
