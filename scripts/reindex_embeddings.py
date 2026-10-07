"""Переиндексация чанков эмбеддингами: python scripts/reindex_embeddings.py

Первый запуск скачивает модель в data/hf_cache (внутри проекта), затем кодирует
все чанки и сохраняет векторы рядом с текстами (data/vector_store/embeddings.pkl).
Повторный запуск пересчитывает индекс принудительно (--force).

Модель и кэш берутся из настроек: EMBEDDING_MODEL, EMBEDDING_CACHE_DIR.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.config import settings  # noqa: E402
from app.knowledge_base.vector_store import VectorStore  # noqa: E402


def main() -> int:
    os.environ["VECTOR_BACKEND"] = "embeddings"  # переиндексация только эмбеддингами
    t0 = time.time()
    store = VectorStore(settings.CHROMA_DIR)
    print(f"бэкенд: {store.backend_name()}")
    print(f"чанков в сторе: {len(store.docs)}")
    if store.backend != "embeddings":
        print(f"ОШИБКА: {store.backend_note or 'эмбеддинги недоступны'}")
        return 2
    if not store.docs:
        print("ОШИБКА: стор пуст — сначала загрузите протоколы (scripts/ingest_pdf.py)")
        return 1

    n = store.reindex_embeddings(force=True)
    dt = time.time() - t0
    print(f"проиндексировано векторов: {n} за {dt:.1f} с ({n / max(dt, 0.001):.0f} чанков/с)")

    # Контрольный запрос: индекс должен сразу отдавать осмысленное
    probe = "острый средний отит у ребёнка: антибиотик"
    hits = store.search(probe, k=3)
    print("\nпроверка поиска:", probe)
    for h in hits:
        print(f"  {h['score']:.3f}  {h.get('nosology', '')[:40]:42} [{h.get('section', '')}]")
    print(f"\nфайл векторов: {store._vec_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
