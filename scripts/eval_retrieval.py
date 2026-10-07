"""Замер качества поиска по золотому набору ЛОР-вопросов.

Зачем: «красивый интерфейс» не спасает, если по вопросу врача не находится
нужный протокол или нужный раздел. Скрипт считает честные метрики до и после
смены поискового бэкенда (TF-IDF / embeddings) и калибрует порог отказа по
распределению скоров, а не «на глаз».

Запуск:
    python scripts/eval_retrieval.py                      # текущий бэкенд из .env
    VECTOR_BACKEND=embeddings python scripts/eval_retrieval.py
    python scripts/eval_retrieval.py --json docs/eval-tfidf.json --show-fails

Метрики:
    recall@k      — доля in-domain вопросов, где нужный протокол попал в топ-k
    MRR@k         — средний обратный ранг первого правильного протокола
    section@k     — доля вопросов, где в топ-k есть чанк ожидаемого раздела
    false-refusal — доля in-domain вопросов, на которые система честно отказала
    out-refusal   — доля вне-доменных вопросов, отсечённых (чем выше, тем лучше)
"""
import argparse
import json
import os
import sys
from statistics import mean, median

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_GOLDEN = os.path.join(ROOT, "data", "eval", "lor_retrieval_golden.json")


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace("ё", "е").split())


def _doc_names(chunk: dict) -> str:
    return _norm(" | ".join(str(chunk.get(f, "")) for f in ("nosology", "document", "title")))


def _matches(chunk: dict, expected: list[str]) -> bool:
    names = _doc_names(chunk)
    return any(_norm(e) in names for e in expected)


def run(golden_path: str, k: int, threshold: float | None, show_fails: bool,
        routing: bool = True, general_cap: int | None = None) -> dict:
    from app.core.config import settings
    from app.knowledge_base.vector_store import VectorStore
    from app.rag.anti_hallucination import effective_threshold, should_refuse
    from app.rag.retriever import retrieve

    data = json.load(open(golden_path, encoding="utf-8"))
    vs = VectorStore(settings.CHROMA_DIR)
    # порог берём тот же, что приложение (он зависит от шкалы бэкенда)
    th = effective_threshold(vs.backend) if threshold is None else threshold
    backend = vs.backend_name()
    print(f"Поисковый бэкенд: {backend} | порог отказа: {th} | k={k} | маршрутизация: {routing} | general_cap: {general_cap}")
    print(f"Золотой набор: {golden_path}\n")

    rows = []
    for item in data["items"]:
        chunks = retrieve(vs, item["q"], k=k, general_cap=general_cap) if routing else vs.search(item["q"], k=k)
        top = max((c.get("score", 0) for c in chunks), default=0.0)
        refused = should_refuse(chunks, th, item["q"])
        rank = next((i + 1 for i, c in enumerate(chunks) if _matches(c, item.get("protocols") or ["\0"])), None)
        sections = [c.get("section", "") for c in chunks]
        want = item.get("sections") or ([item["section"]] if item.get("section") else [])
        section_hit = None if not want else any(w in sections for w in want)
        section_hit_relaxed = None if not want else any(w in sections or "general" in sections for w in want)
        rows.append({
            "id": item["id"], "kind": item["kind"], "q": item["q"],
            "top_score": round(top, 4), "rank": rank, "refused": refused,
            "section_hit": section_hit, "section_hit_relaxed": section_hit_relaxed,
            "sections": sections,
            "docs": [c.get("nosology") or c.get("document") for c in chunks],
        })

    ind = [r for r in rows if r["kind"] == "in_domain"]
    out = [r for r in rows if r["kind"] == "out_of_domain"]
    hits = [r for r in ind if r["rank"]]
    sec = [r for r in ind if r["section_hit"] is not None]
    sec_rel = [r for r in ind if r["section_hit_relaxed"] is not None]

    summary = {
        "backend": backend,
        "threshold": th,
        "k": k,
        "n_in_domain": len(ind),
        "n_out_of_domain": len(out),
        "recall_at_k": round(len(hits) / max(1, len(ind)), 4),
        "mrr_at_k": round(mean([1.0 / r["rank"] for r in hits]) if hits else 0.0, 4),
        "recall_at_1": round(sum(1 for r in ind if r["rank"] == 1) / max(1, len(ind)), 4),
        "section_at_k": round(sum(1 for r in sec if r["section_hit"]) / max(1, len(sec)), 4),
        # Главная метрика содержания: и протокол верный, и нужный раздел в топ-k
        "protocol_and_section_at_k": round(
            sum(1 for r in ind if r["rank"] and r["section_hit"]) / max(1, len(ind)), 4),
        "section_at_k_relaxed": round(sum(1 for r in sec_rel if r["section_hit_relaxed"]) / max(1, len(sec_rel)), 4),
        "routing": routing,
        "general_cap": general_cap,
        "false_refusal_rate": round(sum(1 for r in ind if r["refused"]) / max(1, len(ind)), 4),
        "out_refusal_rate": round(sum(1 for r in out if r["refused"]) / max(1, len(out)), 4),
        "top_score_in_domain": {
            "min": round(min((r["top_score"] for r in ind), default=0), 4),
            "median": round(median([r["top_score"] for r in ind]), 4) if ind else 0,
            "max": round(max((r["top_score"] for r in ind), default=0), 4),
        },
        "top_score_out_of_domain": {
            "median": round(median([r["top_score"] for r in out]), 4) if out else 0,
            "max": round(max((r["top_score"] for r in out), default=0), 4),
        },
    }

    print("── Итог " + "─" * 60)
    for key, val in summary.items():
        print(f"  {key:24} {val}")
    print(f"\n  самая слабая in-domain выборка (топ-3 по низкому скору):")
    for r in sorted(ind, key=lambda x: x["top_score"])[:3]:
        print(f"    {r['top_score']:.3f}  rank={r['rank']}  {r['q'][:70]}")
    if show_fails:
        print("\n── Промахи (нет нужного протокола в топ-k) " + "─" * 25)
        for r in ind:
            if not r["rank"]:
                print(f"  ✗ {r['q'][:70]}\n     получено: {', '.join(str(d)[:34] for d in r['docs'][:3])}")
        for r in ind:
            if r["rank"] and not r["section_hit"]:
                print(f"  ~ раздел не тот: {r['q'][:60]} → {r['sections'][:4]}")
    return {"summary": summary, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description="Замер качества поиска ЛОРАИ")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--threshold", type=float, default=None, help="по умолчанию из settings.LLM_THRESHOLD")
    ap.add_argument("--json", default="", help="куда сохранить отчёт (JSON)")
    ap.add_argument("--show-fails", action="store_true")
    ap.add_argument("--no-routing", action="store_true",
                    help="выключить маршрутизацию вопроса по разделам (для сравнения)")
    ap.add_argument("--general-cap", type=int, default=None,
                    help="предел обзорных чанков в топ-k при известном разделе")
    args = ap.parse_args()

    report = run(args.golden, args.k, args.threshold, args.show_fails,
                 routing=not args.no_routing, general_cap=args.general_cap)
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)) or ".", exist_ok=True)
        json.dump(report, open(args.json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\nОтчёт сохранён: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
