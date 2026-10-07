"""Проверка разметки разделов в поисковом индексе.

Разметку ставит эвристика по заголовкам (`build_index_chunks`), и от неё зависит
маршрутизация вопроса на главу протокола. Скрипт печатает:
  1) статистику сегментов (сколько раз детектор «переключался» на документ —
     много переключений означает дребезг на коротких строках);
  2) детерминированную выборку чанков по разделам для ручной проверки;
  3) лексический индикатор: доля чанков, где слова раздела доминируют.

Запуск: python scripts/check_section_labels.py [--docs 3] [--per-section 3]
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

SECTIONS = ["definition", "diagnostics", "treatment", "referral_criteria", "prevention", "complications"]

# Слова-индикаторы разделов: если чанк помечен разделом, в нём ожидаем свою лексику.
VOCAB = {
    "definition": r"определен|этиологи|патогенез|классификац|распространенн|код по мкб",
    "diagnostics": r"жалоб|анамнез|осмотр|диагност|обследован|отоскоп|аудиометр|критери|симптом",
    "treatment": r"лечен|терапи|рекоменд|препарат|доз|операц|назнач|антибактериальн",
    "referral_criteria": r"госпитализ|показани|направлен|критери|стационар",
    "prevention": r"профилактик|вакцин|диспансер|наблюдени",
    "complications": r"осложнен|риск|прогноз|неблагоприятн",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=3, help="сколько протоколов показать")
    ap.add_argument("--per-section", type=int, default=3, help="сколько чанков на раздел")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    from app.core.config import settings
    from app.knowledge_base.vector_store import VectorStore

    store = VectorStore(settings.CHROMA_DIR)
    docs = store.docs
    print(f"чанков в индексе: {len(docs)} | бэкенд: {store.backend_name()}\n")

    by_doc = {}
    for d in docs:
        by_doc.setdefault(d.get("document") or d.get("nosology"), []).append(d)

    # 1) дребезг детектора: сколько раз раздел меняется внутри документа
    print("── Переключения разделов внутри документа (дребезг заголовков) ──")
    for name, chunks in list(by_doc.items())[:8]:
        seq = [c.get("section") for c in chunks]
        switches = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        dist = Counter(seq)
        print(f"  {name[:44]:46} чанков {len(chunks):4} переключений {switches:3} | "
              f"{dict(dist.most_common(4))}")

    # 2) лексический индикатор по всему индексу
    print("\n── Лексический индикатор (есть ли в чанке своя лексика раздела) ──")
    for sec in SECTIONS:
        subset = [c for c in docs if c.get("section") == sec]
        if not subset:
            continue
        rx = re.compile(VOCAB[sec], re.I)
        hit = sum(1 for c in subset if rx.search(c["text"][:1200]))
        print(f"  {sec:18} чанков {len(subset):4} со своей лексикой {hit:4} ({hit / len(subset) * 100:3.0f}%)")

    # 3) детерминированная выборка для ручного чтения
    import random
    rnd = random.Random(args.seed)
    print(f"\n── Выборка для ручной проверки ({args.docs} протокола) ──")
    for name in list(by_doc)[:args.docs]:
        print(f"\n### {name}")
        for sec in SECTIONS:
            subset = [c for c in by_doc[name] if c.get("section") == sec]
            if not subset:
                continue
            for c in rnd.sample(subset, min(args.per_section, len(subset))):
                head = re.sub(r"\s+", " ", c["text"])[:190]
                print(f"  [{sec}] стр.{c.get('page_range')}: {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
