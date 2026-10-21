"""Личные данные врача: история запросов, оценки ответов, избранное."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.deps import auth, uid
from ..knowledge_base import repository as repo

router = APIRouter(tags=["account"])


@router.get("/history")
def history(limit: int = 20, scope: str = "own", user: dict = Depends(auth)):
    """История запросов. По умолчанию — только свои; `scope=all` — админу.

    До 1.3.1 эндпоинт возвращал запросы всей клиники любому вошедшему: в
    QueryLog не было автора, фильтровать было нечем.
    """
    if scope == "all":
        if user.get("role") != "admin":
            raise HTTPException(403, "Только админ")
        return {"items": repo.get_history(limit), "scope": "all"}
    return {"items": repo.get_history(limit, user=uid(user)), "scope": "own"}


class FeedbackIn(BaseModel):
    query: str
    vote: int
    comment: str = ""


@router.post("/feedback")
def feedback(b: FeedbackIn, user: dict = Depends(auth)):
    """Оценка ответа 👍/👎 (Excellence-4: только сбор данных для анализа)."""
    if b.vote not in (1, -1):
        raise HTTPException(400, "vote должен быть 1 или -1")
    if not b.query.strip():
        raise HTTPException(400, "Пустой query")
    return repo.add_feedback(user.get("sub", "doctor"), b.query, b.vote, b.comment)


class FavIn(BaseModel):
    doc_id: str
    note: str = ""


@router.post("/favorites")
def add_fav(b: FavIn, user: dict = Depends(auth)):
    return repo.add_favorite(user.get("sub", "doctor"), b.doc_id, b.note)


@router.get("/favorites")
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


@router.delete("/favorites/{fav_id}")
def del_fav(fav_id: int, user: dict = Depends(auth)):
    if not repo.remove_favorite(user.get("sub", "doctor"), fav_id):
        raise HTTPException(404, "Не найдено")
    return {"ok": True}
