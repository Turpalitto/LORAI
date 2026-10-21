"""Админка: загрузка протоколов, документы, учётки, журнал, статистика."""
import os
import uuid

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Request,
                     UploadFile)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core.cache import avg_latency, cache
from ..core.config import DISCLAIMER, settings
from ..core.deps import admin_only, client_ip, uid
from ..core.logging import get_request_id
from ..core.ratelimit import limiter
from ..knowledge_base import repository as repo
from ..rag.generator import vs
from ..services.uploads import doc_lock, process_upload

router = APIRouter(tags=["admin"])


@router.get("/admin/health")
def admin_health(user: dict = Depends(admin_only)):
    """Детальная проверка зависимостей: БД, векторное хранилище, LLM, кэш."""
    try:
        docs = len(repo.list_documents())
        db_ok: bool | str = True
    except Exception as e:
        docs = -1
        db_ok = f"DB error: {e}"
    try:
        v = vs()
        chunks = v.chroma.count() if v.chroma is not None else len(v.docs)
        vec_ok: bool | str = True
    except Exception as e:
        chunks = -1
        vec_ok = f"vector error: {e}"
    llm_configured = settings.LLM_PROVIDER != "mock" and bool(settings.LLM_API_KEY)
    try:
        retrieval = vs().stats()
    except Exception as e:
        retrieval = {"backend": "недоступен", "note": str(e)[:120]}
    return {"ok": db_ok is True and vec_ok is True, "db": db_ok, "documents": docs,
            "vector_store": vec_ok, "chunks": chunks, "retrieval": retrieval,
            "llm_configured": llm_configured,
            "llm_mode": ("api:" + settings.LLM_PROVIDER) if llm_configured else "mock",
            "cache": cache.stats(), "avg_latency_ms": avg_latency(),
            "version": settings.APP_VERSION,
            "retention": {"query_days": settings.QUERY_RETENTION_DAYS,
                          "audit_days": settings.AUDIT_RETENTION_DAYS},
            "disclaimer": DISCLAIMER}


@router.post("/admin/upload")
@router.post("/admin/upload-pdf")
@limiter.limit("10/minute")
def upload(request: Request, background: BackgroundTasks, f: UploadFile,
           user: dict = Depends(admin_only)):
    # Имя файла приходит от клиента и может содержать путь ("../../etc/x.pdf"):
    # раньше оно подставлялось в (raw_dir / filename).write_bytes() как есть —
    # запись за пределы каталога загрузок. Оставляем только базовое имя.
    fname = os.path.basename((f.filename or "").replace("\\", "/")).strip() or "upload.pdf"
    if not fname.lower().endswith((".pdf", ".txt")):
        raise HTTPException(400, "Только PDF/TXT")
    blob = f.file.read()
    if len(blob) > 50 * 1024 * 1024:
        raise HTTPException(400, "Файл больше 50 МБ")
    if fname.lower().endswith(".pdf") and not blob[:4] == b"%PDF":
        raise HTTPException(400, "Не похоже на PDF")
    # Дедупликация: повторная загрузка того же файла обновляет запись, а не
    # плодит дубликаты. Проверка и создание — под замком по имени файла: два
    # одновременных запроса иначе оба не находили существующий документ и
    # создавали два разных id на один файл (проверено, воспроизводилось).
    with doc_lock("name:" + fname):
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
    background.add_task(process_upload, blob, fname, document_id, uid(user),
                        get_request_id())
    repo.audit(uid(user), "document.upload", target=document_id,
               detail=("reupload:" if existing else "new:") + fname, ip=client_ip(request))
    return JSONResponse(status_code=202, content={
        "document_id": document_id, "status": "processing", "title": fname,
        "duplicate": bool(existing), "poll": f"/protocols/{document_id}",
    })


@router.get("/admin/documents")
def docs(user: dict = Depends(admin_only)):
    """Все документы, включая те, что ещё разбираются в фоне (status=processing)."""
    return {"items": repo.list_documents(include_processing=True)}


class DocPatch(BaseModel):
    nosology: str | None = None
    icd10_codes: list[str] | None = None
    approval_year: int | None = None
    needs_review: bool | None = None


@router.patch("/admin/documents/{doc_id}")
def patch_doc(doc_id: str, b: DocPatch, request: Request,
              user: dict = Depends(admin_only)):
    patch = {k: v for k, v in b.model_dump().items() if v is not None}
    d = repo.update_document(doc_id, patch)
    if not d:
        raise HTTPException(404, "Не найдено")
    repo.audit(uid(user), "document.patch", target=doc_id,
               detail="changed=" + ",".join(patch), ip=client_ip(request))
    return d


@router.get("/admin/stats")
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


@router.get("/admin/users")
def admin_users(user: dict = Depends(admin_only)):
    """Список учёток. Хеши паролей наружу не отдаются."""
    return {"items": repo.list_users()}


@router.post("/admin/users", status_code=201)
def admin_create_user(b: UserIn, request: Request, user: dict = Depends(admin_only)):
    try:
        created = repo.create_user(b.email, b.password, b.role, b.full_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    repo.audit(uid(user), "user.create", target=created["email"],
               detail=f"role={created['role']}", ip=client_ip(request))
    return created


@router.patch("/admin/users/{email}")
def admin_patch_user(email: str, b: UserPatch, request: Request,
                     user: dict = Depends(admin_only)):
    """Правка учётки: роль, активность, ФИО, пароль.

    Две защиты от самоблокировки клиники: нельзя отключить/понизить себя и
    нельзя оставить систему без активного администратора. Пароль в журнал
    не пишется — только факт смены.
    """
    target = email.strip().lower()
    me = uid(user).lower()
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
               ip=client_ip(request))
    return updated


@router.get("/admin/audit")
def admin_audit(limit: int = 100, action: str | None = None,
                actor: str | None = None, user: dict = Depends(admin_only)):
    """Журнал действий: входы, загрузки/правки протоколов, управление учётками."""
    return {"items": repo.list_audit(limit, action, actor)}


@router.post("/admin/maintenance/purge")
def admin_purge(user: dict = Depends(admin_only)):
    """Ручная очистка по политике хранения (та же, что при старте)."""
    q = repo.purge_old_queries(settings.QUERY_RETENTION_DAYS)
    a = repo.purge_old_audit(settings.AUDIT_RETENTION_DAYS)
    repo.audit(uid(user), "maintenance.purge", target="query_log,audit_log",
               detail=f"queries={q},audit={a}")
    return {"queries_deleted": q, "audit_deleted": a,
            "query_retention_days": settings.QUERY_RETENTION_DAYS,
            "audit_retention_days": settings.AUDIT_RETENTION_DAYS}
