"""Служебные эндпоинты: публичная проверка живости."""
from fastapi import APIRouter

from ..core.config import settings
from ..knowledge_base import repository as repo
from ..rag.generator import vs

router = APIRouter(tags=["system"])


@router.get("/health")
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
