"""Ответ-уровневый замер: что реально получает врач на свои вопросы.

Метрики поиска (recall/разделы) — прокси. Здесь измеряем конечный результат:
на N реальных ЛОР-вопросов считаем, сколько ответов содержат рецепт/тактику,
сколько — честный отказ и сколько — «в контексте нет информации» (то есть
поиск не донёс нужный кусок до модели).

Запуск (нужен живой ключ LLM в .env):
    VECTOR_BACKEND=tfidf     python scripts/eval_answers.py --limit 8
    VECTOR_BACKEND=embeddings python scripts/eval_answers.py --limit 8 --json docs/eval/answers-emb.json

Важно: скрипт делает РЕАЛЬНЫЕ вызовы LLM (деньги/лимиты) — по умолчанию 8 вопросов.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOLDEN = os.path.join(ROOT, "data", "eval", "lor_retrieval_golden.json")

# Маркеры «модель не нашла данных» — честный ответ, но признак промаха поиска.
NO_DATA = re.compile(
    r"нет информаци|не найдена|не найдено|не содержит|информаци[яи] по этому вопросу отсутств|"
    r"в предоставленном контексте|в контексте нет", re.I)


JUDGE_SYS = (
    "Ты — строгий рецензент медицинского справочного ассистента. Тебе дают вопрос врача, "
    "выдержки из клинических рекомендаций (единственный допустимый источник) и ответ ассистента. "
    "Оцени строго и не делай скидок:\n"
    "- grounded: опирается ли ответ ТОЛЬКО на выдержки (true/false); любые факты и цифры вне выдержек → false;\n"
    "- answers: отвечает ли ответ на вопрос по существу — \"yes\" | \"partial\" | \"no\";\n"
    "- notes: одна короткая фраза по-русски, в чём сильная или слабая сторона.\n"
    "Верни ТОЛЬКО JSON без пояснений: {\"grounded\": true, \"answers\": \"yes\", \"notes\": \"...\"}"
)


def judge_answer(q: str, chunks: list[dict], answer: str) -> dict:
    """Независимая (структурированная) оценка ответа тем же LLM-провайдером."""
    import re as _re
    from app.llm_clients.mock import get_client
    excerpts = "\n---\n".join((c.get("text") or "")[:900] for c in (chunks or [])[:5])
    usr = f"ВОПРОС ВРАЧА:\n{q}\n\nВЫДЕРЖКИ ИЗ КЛИНИЧЕСКИХ РЕКОМЕНДАЦИЙ:\n{excerpts or '(пусто)'}\n\nОТВЕТ АССИСТЕНТА:\n{answer}"
    try:
        raw = get_client().complete(JUDGE_SYS, usr)
        m = _re.search(r"\{.*\}", raw, _re.S)
        if m:
            j = json.loads(m.group(0))
            return {"grounded": bool(j.get("grounded")), "answers": str(j.get("answers", "no")).lower(),
                    "notes": str(j.get("notes", ""))[:200]}
    except Exception as e:
        return {"grounded": None, "answers": "error", "notes": str(e)[:120]}
    return {"grounded": None, "answers": "unparsed", "notes": raw[:120] if 'raw' in dir() else ""}


def classify(res: dict) -> str:
    if res.get("refused"):
        return "refusal"
    if res.get("needs_clarification"):
        return "clarify"   # уточняющий вопрос — легитимное поведение, не промах
    text = res.get("answer") or ""
    if not text.strip():
        return "empty"
    if NO_DATA.search(text):
        return "no_data"
    return "answer"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8, help="сколько вопросов (реальные вызовы LLM)")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--json", default="")
    ap.add_argument("--golden", default=GOLDEN)
    ap.add_argument("--judge", action="store_true",
                    help="оценивать ответы отдельным LLM-судьёй (структурированная рубрика)")
    args = ap.parse_args()

    from app.core.config import settings
    from app.rag.generator import answer, vs

    data = json.load(open(args.golden, encoding="utf-8"))
    items = [i for i in data["items"] if i["kind"] == "in_domain"][args.offset:args.offset + args.limit]
    backend = vs().backend_name()
    print(f"Бэкенд поиска: {backend} | модель LLM: {settings.LLM_MODEL} | вопросов: {len(items)}\n")

    rows, t_all = [], 0.0
    for it in items:
        t0 = time.monotonic()
        try:
            res = answer(it["q"])
        except Exception as e:
            res = {"answer": f"ОШИБКА: {e}", "refused": False}
        dt = time.monotonic() - t0
        t_all += dt
        kind = classify(res)
        verdict = None
        if args.judge and kind in ("answer", "no_data"):
            verdict = judge_answer(it["q"], res.get("sources") or [], res.get("answer") or "")
        rows.append({"id": it["id"], "q": it["q"], "kind": kind, "sec": dt, "judge": verdict,
                     "top_score": res.get("top_score"), "answer_head": (res.get("answer") or "")[:160]})
        tail = ""
        if verdict:
            tail = f" | судья: answers={verdict['answers']} grounded={verdict['grounded']}"
        print(f"  [{kind:8}] {dt:4.1f}с score={res.get('top_score')}  {it['q'][:52]}{tail}")
        if kind in ("no_data", "refusal"):
            print(f"             → {(res.get('answer') or '')[:110]}")

    from collections import Counter
    c = Counter(r["kind"] for r in rows)
    judged = [r["judge"] for r in rows if r.get("judge")]
    jc = Counter(j["answers"] for j in judged)
    summary = {
        "backend": backend,
        "questions": len(rows),
        "answer_rate": round(c["answer"] / max(1, len(rows)), 4),
        "no_data_rate": round(c["no_data"] / max(1, len(rows)), 4),
        "refusal_rate": round(c["refusal"] / max(1, len(rows)), 4),
        "clarify_rate": round(c["clarify"] / max(1, len(rows)), 4),
        "counts": dict(c),
        "avg_seconds": round(t_all / max(1, len(rows)), 2),
        "judged": len(judged),
        "judge_answers_yes_rate": round(jc.get("yes", 0) / max(1, len(judged)), 4),
        "judge_partial_rate": round(jc.get("partial", 0) / max(1, len(judged)), 4),
        "judge_no_rate": round(jc.get("no", 0) / max(1, len(judged)), 4),
        "judge_grounded_rate": round(sum(1 for j in judged if j.get("grounded")) / max(1, len(judged)), 4),
    }
    print("\n── Итог " + "─" * 60)
    for k, v in summary.items():
        print(f"  {k:16} {v}")
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)) or ".", exist_ok=True)
        json.dump({"summary": summary, "rows": rows}, open(args.json, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"\nОтчёт: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
