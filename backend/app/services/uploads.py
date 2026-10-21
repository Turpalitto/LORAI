"""Фоновая обработка загруженных протоколов.

Вынесено из `main.py`: разбор PDF не относится к HTTP-слою, а замки и
временные файлы нужны и тестам, и админским роутам.
"""
import os
import tempfile
import threading

from ..core.cache import cache
from ..core.config import ROOT_DIR
from ..core.logging import log, reset_request_id, set_request_id
from ..ingestion.pipeline import process_pdf
from ..knowledge_base import repository as repo
from ..rag.generator import vs

# Замки по document_id: две загрузки одного и того же файла (или повторная
# загрузка во время разбора) шли параллельно и перетирали чанки друг друга —
# последняя запись могла остаться с нулём чанков. Разбор одного документа
# сериализуем, разные документы по-прежнему обрабатываются параллельно.
_UPLOAD_LOCKS: dict[str, threading.Lock] = {}
_UPLOAD_LOCKS_GUARD = threading.Lock()


def doc_lock(key: str) -> threading.Lock:
    """Замок по ключу: `document_id` для разбора, `name:<файл>` для дедупа."""
    with _UPLOAD_LOCKS_GUARD:
        return _UPLOAD_LOCKS.setdefault(key, threading.Lock())


def process_upload(blob: bytes, fname: str, document_id: str, actor: str = "",
                   rid: str = "") -> None:
    with doc_lock(document_id):
        _process_upload_unlocked(blob, fname, document_id, actor, rid)


def _process_upload_unlocked(blob: bytes, fname: str, document_id: str,
                             actor: str = "", rid: str = "") -> None:
    """Фоновая обработка загруженного файла.

    Раньше 70-страничный PDF разбирался прямо в обработчике: воркер занят
    секунды-десятки секунд (с OCR — минуты), клиент всё это время ждёт ответа.
    Теперь запись создаётся сразу со статусом processing, а разбор идёт после
    ответа; админка опрашивает /protocols/{id}.
    """
    from ..llm_clients.mock import MockLLMClient

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
