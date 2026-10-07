"""Пересборка поискового индекса без дублей: python scripts/reindex_corpus.py [--src "лор клинреки"]

Что делает:
  1) читает исходные PDF клинических рекомендаций и режет каждый документ так,
     чтобы текст попал в индекс РОВНО ОДИН РАЗ, с меткой своего раздела;
  2) сопоставляет PDF с записями в БД по нозологии (сама БД не изменяется —
     админка, чек-листы, шаблоны продолжают работать как раньше);
  3) складывает старый индекс в backup-папку и пишет новый.

Зачем: прежний индекс на 84 % состоял из дублей `general` (полный текст плюс
те же разделы), из-за чего в топ-6 попадали обзорные куски, а нужный раздел
(лечение/диагностика) до модели не доезжал.

После пересборки: python scripts/reindex_embeddings.py (если включены эмбеддинги).
"""
import argparse
import os
import re
import shutil
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def _nosology_from_filename(name: str) -> str:
    base = os.path.splitext(name)[0]
    return _norm(base.split("_")[0])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(ROOT, "лор клинреки"))
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    from app.core.config import settings
    from app.ingestion.pdf_loader import load_pages
    from app.ingestion.pipeline import build_index_chunks
    from app.knowledge_base import repository as repo
    from app.knowledge_base.vector_store import VectorStore

    if not os.path.isdir(args.src):
        print(f"ОШИБКА: нет каталога с PDF: {args.src}")
        return 2

    store = VectorStore(settings.CHROMA_DIR)
    old_count = len(store.docs)
    docs = repo.list_documents()
    by_nosology = {_norm(d["nosology"]): d for d in docs}
    print(f"документов в БД: {len(docs)} | индекс сейчас: {len(store.docs)} чанков")

    pdfs = sorted(f for f in os.listdir(args.src) if f.lower().endswith(".pdf"))
    print(f"PDF найдено: {len(pdfs)}")

    prepared: list[tuple[dict, list[dict]]] = []
    unmatched: list[str] = []
    for name in pdfs:
        key = _nosology_from_filename(name)
        doc = by_nosology.get(key)
        if doc is None:
            # мягкое сопоставление: по вхождению нозологии в имя файла
            doc = next((d for k, d in by_nosology.items() if k and k in _norm(name)), None)
        if doc is None:
            unmatched.append(name)
            continue
        t0 = time.time()
        pages = load_pages(os.path.join(args.src, name))
        chunks = build_index_chunks(pages)
        prepared.append((doc, chunks))
        print(f"  {doc['nosology'][:44]:46} страниц {len(pages):3} → чанков {len(chunks):4} "
              f"({time.time() - t0:.1f}с, разделы: {dict(Counter(c['section'] for c in chunks).most_common(4))})")

    if not prepared:
        print("ОШИБКА: ни один PDF не сопоставлен с БД")
        return 1
    if unmatched:
        print(f"НЕ сопоставлены (пропущены): {unmatched}")

    # --- собираем новый индекс ---
    new_docs: list[dict] = []
    for doc, chunks in prepared:
        meta = {"title": doc["title"], "nosology": doc["nosology"], "document": doc["title"],
                "icd10_codes": doc["icd10_codes"]}
        for c in chunks:
            new_docs.append({"text": c["text"], **meta,
                             "section": c.get("section", ""), "page_range": c.get("page_range", [])})

    if not args.no_backup:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        bdir = os.path.join(settings.CHROMA_DIR, f"backup-{stamp}")
        os.makedirs(bdir, exist_ok=True)
        for f in ("fallback.pkl", "embeddings.pkl"):
            src = os.path.join(settings.CHROMA_DIR, f)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(bdir, f))
        print(f"бэкап прежнего индекса: {bdir}")

    store.docs = new_docs
    store._vectors = None
    store._index_all()
    store._save()
    try:
        os.remove(store._vec_path())  # старые векторы не соответствуют новым чанкам
    except OSError:
        pass

    print(f"\nновый индекс: {len(store.docs)} чанков (было {old_count})")
    dist = Counter(d.get("section", "?") for d in store.docs)
    print("по разделам:", dict(dist.most_common()))
    print(f"доля обзорных (general): {dist.get('general', 0) / max(1, len(store.docs)) * 100:.0f}%")
    print("\nдальше: python scripts/reindex_embeddings.py — и замер scripts/eval_retrieval.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
