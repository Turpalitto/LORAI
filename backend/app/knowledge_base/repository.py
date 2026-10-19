from sqlalchemy import create_engine, select, func, desc, and_, or_
from sqlalchemy.orm import Session
from .models import Base, Document, QueryLog, Favorite, Feedback, User, AuditLog
from ..core.config import settings
from ..core.migrations import ensure_schema
from ..core.security import hash_pw
eng = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {})
# Схему приводит к head alembic (см. core/migrations.py). create_all оставлен
# только для тестов: иначе схема и миграции расходятся, и новая колонка
# появляется лишь у того, кто вручную вспомнил про alembic.
SCHEMA_STATE = ensure_schema()
def save_document(doc: dict):
    with Session(eng) as s:
        d = Document(id=doc["document_id"], title=doc["title"], nosology=doc["nosology"],
            icd10_codes=doc.get("icd10_codes", []), approval_year=doc.get("approval_year", 2024),
            revision_year=doc.get("revision_year"), source_file=doc.get("source_file",""),
            status=doc.get("processing_status","processed"), data=doc.get("sections",{}),
            full_text=doc.get("_full_text","")[:60000],
            confidence=doc.get("extraction_confidence","medium"),
            needs_review=doc.get("needs_manual_review", False))
        s.merge(d); s.commit()
def list_documents(include_processing: bool = False) -> list[dict]:
    """Список документов. По умолчанию без тех, что ещё обрабатываются в фоне:
    иначе врач видит в каталоге пустую карточку свежей загрузки."""
    with Session(eng) as s:
        stmt = select(Document)
        if not include_processing:
            stmt = stmt.where(Document.status != "processing")
        rows = s.execute(stmt).scalars().all()
        return [{"document_id": r.id, "title": r.title, "nosology": r.nosology,
                 "icd10_codes": r.icd10_codes, "approval_year": r.approval_year,
                 "status": r.status, "confidence": r.confidence,
                 "needs_review": r.needs_review} for r in rows]
def get_document(doc_id: str) -> dict | None:
    with Session(eng) as s:
        r = s.get(Document, doc_id)
        if not r: return None
        return {"document_id": r.id, "title": r.title, "nosology": r.nosology,
                "icd10_codes": r.icd10_codes, "approval_year": r.approval_year,
                "status": r.status, "confidence": r.confidence,
                "needs_review": r.needs_review,
                "sections": r.data, "full_text": r.full_text}
def update_document(doc_id: str, patch: dict) -> dict | None:
    with Session(eng) as s:
        r = s.get(Document, doc_id)
        if not r: return None
        if "nosology" in patch: r.nosology = patch["nosology"]
        if "icd10_codes" in patch: r.icd10_codes = patch["icd10_codes"]
        if "approval_year" in patch: r.approval_year = patch["approval_year"]
        if "needs_review" in patch: r.needs_review = patch["needs_review"]
        if "status" in patch: r.status = patch["status"]
        if "confidence" in patch: r.confidence = patch["confidence"]
        s.commit()
        return {"document_id": r.id, "title": r.title, "nosology": r.nosology,
                "icd10_codes": r.icd10_codes, "approval_year": r.approval_year,
                "status": r.status, "confidence": r.confidence,
                "needs_review": r.needs_review}
def search_protocols(q: str) -> list[dict]:
    """Поиск по документам. SQL-пушдаун: LIKE-фильтр по title/nosology/full_text
    на стороне БД вместо прежнего Python full-scan (22 × 60k символов на каждый
    запрос). Токены ≤3 символов (МКБ-коды «H66», «J01») ищутся целиком."""
    ql = (q or "").strip().lower()
    if not ql:
        return []
    terms = [t for t in ql.split() if t] or [ql]
    with Session(eng) as s:
        # Каждый термин должен встретиться хотя бы в одном из полей (AND между
        # терминами, OR между полями — как прежний haystack, но в SQL).
        cond = and_(*[
            or_(
                func.lower(Document.title).contains(t),
                func.lower(Document.nosology).contains(t),
                func.lower(Document.full_text).contains(t),
            ) for t in terms
        ])
        rows = s.execute(select(Document).where(cond)).scalars().all()
        return [{"document_id": r.id, "title": r.title, "nosology": r.nosology,
                 "icd10_codes": r.icd10_codes, "approval_year": r.approval_year,
                 "status": r.status, "confidence": r.confidence,
                 "needs_review": r.needs_review, "sections": r.data} for r in rows]
def log_query(query: str, intent: str, refused: bool, user: str = "guest"):
    with Session(eng) as s:
        s.add(QueryLog(query=query[:2000], intent=intent, refused=refused,
                       user=(user or "guest")[:200]))
        s.commit()


def get_history(limit: int = 20, user: str | None = None) -> list[dict]:
    """История запросов. `user` задан — только его записи; None — все (админ).

    Раньше функция не знала про пользователя, и `/history` отдавал врачу
    запросы всей клиники — с клиническим контекстом, но без имени автора.
    """
    with Session(eng) as s:
        stmt = select(QueryLog).order_by(desc(QueryLog.id)).limit(limit)
        if user:
            stmt = stmt.where(QueryLog.user == user)
        rows = s.execute(stmt).scalars().all()
        return [{"query": r.query, "intent": r.intent, "refused": r.refused,
                 "user": r.user, "at": str(r.created_at)} for r in rows]
def add_favorite(user: str, doc_id: str, note: str = "") -> dict:
    with Session(eng) as s:
        f = Favorite(user=user, doc_id=doc_id, note=note); s.add(f); s.commit()
        return {"ok": True, "id": f.id}
def list_favorites(user: str) -> list[dict]:
    with Session(eng) as s:
        rows = s.execute(select(Favorite).where(Favorite.user == user)).scalars().all()
        return [{"id": r.id, "doc_id": r.doc_id, "note": r.note} for r in rows]

def remove_favorite(user: str, fav_id: int) -> bool:
    """Удалить только свою запись избранного; чужую — False."""
    with Session(eng) as s:
        r = s.get(Favorite, fav_id)
        if not r or r.user != user:
            return False
        s.delete(r); s.commit()
        return True

def add_feedback(user: str, query: str, vote: int, comment: str = "") -> dict:
    with Session(eng) as s:
        f = Feedback(user=user, query=query[:2000], vote=vote, comment=comment[:1000])
        s.add(f); s.commit()
        return {"ok": True, "id": f.id}

def usage_stats(gap_limit: int = 10) -> dict:
    """Аналитика для админа клиники (Excellence-4): использование, пробелы
    базы знаний (частые отказы), сводка оценок."""
    with Session(eng) as s:
        total = s.execute(select(func.count(QueryLog.id))).scalar() or 0
        refused = s.execute(select(func.count(QueryLog.id)).where(QueryLog.refused.is_(True))).scalar() or 0
        gaps = s.execute(
            select(QueryLog.query, func.count(QueryLog.id).label("n"))
            .where(QueryLog.refused.is_(True))
            .group_by(QueryLog.query).order_by(desc("n")).limit(gap_limit)
        ).all()
        up = s.execute(select(func.count(Feedback.id)).where(Feedback.vote == 1)).scalar() or 0
        down = s.execute(select(func.count(Feedback.id)).where(Feedback.vote == -1)).scalar() or 0
        docs = s.execute(select(func.count(Document.id))).scalar() or 0
        return {"documents": docs, "queries_total": total, "queries_refused": refused,
                "refusal_rate": round(refused / total, 3) if total else 0.0,
                "knowledge_gaps": [{"query": q, "count": n} for q, n in gaps],
                "feedback": {"up": up, "down": down}}


# --------------------------------------------------------------------------
# Пользователи и аудит
#
# Раньше учётки жили в dict, собранном из env при старте: добавить врача —
# правка .env + рестарт, сменить пароль — то же, истории действий нет вовсе.
# Теперь БД — источник правды, env используется только для первичного сида.
# --------------------------------------------------------------------------

ROLES = ("admin", "doctor")


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _user_row(r: User, with_hash: bool = False) -> dict:
    out = {"email": r.email, "role": r.role, "active": bool(r.active),
           "full_name": r.full_name or "",
           "created_at": str(r.created_at) if r.created_at else None,
           "last_login_at": str(r.last_login_at) if r.last_login_at else None}
    if with_hash:
        out["pw_hash"] = r.pw_hash
    return out


def get_user(email: str) -> dict | None:
    """Учётка по email (включая хеш пароля — нужен только login)."""
    with Session(eng) as s:
        r = s.get(User, _norm_email(email))
        return _user_row(r, with_hash=True) if r else None


def list_users() -> list[dict]:
    """Все учётки без хешей паролей — для админки."""
    with Session(eng) as s:
        rows = s.execute(select(User).order_by(User.email)).scalars().all()
        return [_user_row(r) for r in rows]


def create_user(email: str, password: str, role: str = "doctor",
                full_name: str = "") -> dict:
    email = _norm_email(email)
    if not email or "@" not in email:
        raise ValueError("Некорректный email")
    if role not in ROLES:
        raise ValueError("Роль должна быть admin или doctor")
    if len(password or "") < 8:
        raise ValueError("Пароль короче 8 символов")
    with Session(eng) as s:
        if s.get(User, email):
            raise ValueError("Пользователь с таким email уже существует")
        u = User(email=email, pw_hash=hash_pw(password), role=role,
                 full_name=full_name[:200])
        s.add(u); s.commit()
        return _user_row(u)


def update_user(email: str, patch: dict) -> dict | None:
    """Правка учётки: роль, активность, ФИО, пароль.

    Пароль приходит открытым текстом и хешируется здесь же — наружу хеш
    не отдаётся никогда.
    """
    email = _norm_email(email)
    with Session(eng) as s:
        u = s.get(User, email)
        if not u:
            return None
        if "role" in patch and patch["role"] is not None:
            if patch["role"] not in ROLES:
                raise ValueError("Роль должна быть admin или doctor")
            u.role = patch["role"]
        if "active" in patch and patch["active"] is not None:
            u.active = bool(patch["active"])
        if "full_name" in patch and patch["full_name"] is not None:
            u.full_name = str(patch["full_name"])[:200]
        if patch.get("password"):
            if len(patch["password"]) < 8:
                raise ValueError("Пароль короче 8 символов")
            u.pw_hash = hash_pw(patch["password"])
        s.commit()
        return _user_row(u)


def count_active_admins() -> int:
    with Session(eng) as s:
        return s.execute(
            select(func.count(User.email)).where(User.role == "admin",
                                                  User.active.is_(True))
        ).scalar() or 0


def touch_login(email: str) -> None:
    from datetime import datetime as _dt
    with Session(eng) as s:
        u = s.get(User, _norm_email(email))
        if u:
            u.last_login_at = _dt.utcnow(); s.commit()


def ensure_default_users() -> int:
    """Идемпотентный сид из env: создаёт недостающие учётки, существующие не
    трогает (иначе смена пароля в админке откатывалась бы при рестарте).

    Вызывается при импорте `app.main` — на пустой БД это первый админ.
    """
    defaults = [{"email": settings.ADMIN_EMAIL, "password": settings.ADMIN_PASSWORD,
                 "role": "admin", "full_name": "Администратор"}]
    if settings.LORAI_DOCTOR_EMAIL and settings.LORAI_DOCTOR_PASSWORD:
        defaults.append({"email": settings.LORAI_DOCTOR_EMAIL,
                         "password": settings.LORAI_DOCTOR_PASSWORD,
                         "role": "doctor", "full_name": ""})
    created = 0
    with Session(eng) as s:
        for d in defaults:
            email = _norm_email(d["email"])
            if not email or s.get(User, email):
                continue
            s.add(User(email=email, pw_hash=hash_pw(d["password"]),
                       role=d["role"], full_name=d.get("full_name", "")))
            created += 1
        if created:
            s.commit()
    return created


def audit(user: str, action: str, target: str = "", detail: str = "",
          ip: str = "") -> None:
    """Запись в журнал действий. Ошибка журнала не должна ломать действие."""
    try:
        with Session(eng) as s:
            s.add(AuditLog(user=(user or "guest")[:200], action=action[:100],
                           target=(target or "")[:300], detail=(detail or "")[:1000],
                           ip=(ip or "")[:64]))
            s.commit()
    except Exception:
        pass


def list_audit(limit: int = 100, action: str | None = None,
               user: str | None = None) -> list[dict]:
    with Session(eng) as s:
        stmt = select(AuditLog).order_by(desc(AuditLog.id)).limit(max(1, min(limit, 1000)))
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if user:
            stmt = stmt.where(AuditLog.user == _norm_email(user))
        rows = s.execute(stmt).scalars().all()
        return [{"id": r.id, "user": r.user, "action": r.action, "target": r.target,
                 "detail": r.detail, "ip": r.ip,
                 "at": str(r.created_at)} for r in rows]


def purge_old_queries(days: int) -> int:
    """Политика хранения: тексты запросов старше N дней удаляются.

    ПДн-фильтр на входе не абсолютен, а клинический текст в БД бессрочно —
    это лишний риск. Аналитика (refused/intent) старше срока тоже не нужна.
    """
    from datetime import datetime as _dt, timedelta as _td
    if days <= 0:
        return 0
    cutoff = _dt.utcnow() - _td(days=days)
    with Session(eng) as s:
        rows = s.execute(select(QueryLog).where(QueryLog.created_at < cutoff)).scalars().all()
        for r in rows:
            s.delete(r)
        s.commit()
        return len(rows)


def purge_old_audit(days: int) -> int:
    from datetime import datetime as _dt, timedelta as _td
    if days <= 0:
        return 0
    cutoff = _dt.utcnow() - _td(days=days)
    with Session(eng) as s:
        rows = s.execute(select(AuditLog).where(AuditLog.created_at < cutoff)).scalars().all()
        for r in rows:
            s.delete(r)
        s.commit()
        return len(rows)


# Первичный сид учёток. Делается при импорте репозитория, а не только в
# app.main: иначе скрипты и тесты, работающие с БД напрямую, видели пустую
# таблицу пользователей. Существующие записи не трогаются.
DEFAULT_USERS_CREATED = ensure_default_users()

