"""Протоколы: каталог, поиск, карточка, чек-листы и шаблоны."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.cache import cache
from ..core.config import DISCLAIMER
from ..core.deps import auth
from ..features import checklist_generator as chk
from ..features import referral_criteria as ref
from ..features import report_templates as tpl
from ..knowledge_base import repository as repo

router = APIRouter(tags=["protocols"])


@router.get("/protocols")
def protocols(q: str = ""):
    # пустой запрос = листинг метаданных (дашборд «протоколы базы»);
    # с запросом — поиск как раньше
    items = repo.list_documents() if not q.strip() else repo.search_protocols(q)
    return {"items": items, "disclaimer": DISCLAIMER}


class SearchProtocolIn(BaseModel):
    q: str = ""
    nosology: str | None = None
    icd10: str | None = None
    symptom: str | None = None


@router.post("/search-protocol")
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


@router.get("/protocols/{doc_id}")
def one_protocol(doc_id: str):
    d = repo.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Не найдено")
    return {**d, "disclaimer": DISCLAIMER}


@router.get("/protocols/{doc_id}/related")
def related(doc_id: str):
    """Похожие протоколы по графу связей нозологий (Excellence-1)."""
    from ..features.nosology_graph import related_protocols
    return {"items": related_protocols(doc_id), "disclaimer": DISCLAIMER}


@router.get("/contradictions")
def contradictions(user: dict = Depends(auth)):
    """Пары протоколов с пересекающимися МКБ и расходящимися назначениями."""
    from ..features.nosology_graph import find_contradictions
    return {"items": find_contradictions(), "disclaimer": DISCLAIMER}


@router.get("/checklist/{doc_id}")
def checklist(doc_id: str):
    d = repo.get_document(doc_id)
    if not d:
        raise HTTPException(404, "Нет протокола")
    return {**chk.build_checklist(d), "disclaimer": DISCLAIMER}


@router.get("/templates/{kind}/{doc_id}")
def template(kind: str, doc_id: str):
    d = repo.get_document(doc_id) or {"nosology": "", "icd10_codes": [],
                                      "title": "", "approval_year": ""}
    return {"text": tpl.render(kind, d), "disclaimer": DISCLAIMER}


class RefIn(BaseModel):
    doc_id: str
    answers: dict


@router.post("/referral-check")
def referral(b: RefIn):
    d = repo.get_document(b.doc_id) or {}
    return {**ref.check_referral(b.answers, d), "disclaimer": DISCLAIMER}
