from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from .models import Base, Document, QueryLog, Favorite
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
    ql = (q or "").lower()
    out = []
    for d in list_documents():
        full = get_document(d["document_id"]) or {}
        hay = (d["title"] + d["nosology"] + str(d["icd10_codes"])
               + full.get("full_text", "") + str(full.get("sections", ""))[:15000]).lower()
        if ql in hay or any(t in hay for t in ql.split() if len(t) > 3):
            out.append({**d, "sections": full.get("sections", {})})
    return out
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
