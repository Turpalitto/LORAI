from sqlalchemy import create_engine, select, func, desc, and_, or_
from sqlalchemy.orm import Session
from .models import Base, Document, QueryLog, Favorite, Feedback
from ..core.config import settings
eng = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {})
Base.metadata.create_all(eng)
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
def list_documents() -> list[dict]:
    with Session(eng) as s:
        rows = s.execute(select(Document)).scalars().all()
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
                "sections": r.data, "full_text": r.full_text}
def update_document(doc_id: str, patch: dict) -> dict | None:
    with Session(eng) as s:
        r = s.get(Document, doc_id)
        if not r: return None
        if "nosology" in patch: r.nosology = patch["nosology"]
        if "icd10_codes" in patch: r.icd10_codes = patch["icd10_codes"]
        if "approval_year" in patch: r.approval_year = patch["approval_year"]
        if "needs_review" in patch: r.needs_review = patch["needs_review"]
        s.commit()
        return {"document_id": r.id, "title": r.title, "nosology": r.nosology,
                "icd10_codes": r.icd10_codes, "approval_year": r.approval_year,
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
def log_query(query: str, intent: str, refused: bool):
    with Session(eng) as s:
        s.add(QueryLog(query=query[:2000], intent=intent, refused=refused)); s.commit()
def get_history(limit: int = 20) -> list[dict]:
    from sqlalchemy import desc
    with Session(eng) as s:
        rows = s.execute(select(QueryLog).order_by(desc(QueryLog.id)).limit(limit)).scalars().all()
        return [{"query": r.query, "intent": r.intent, "refused": r.refused,
                 "at": str(r.created_at)} for r in rows]
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
