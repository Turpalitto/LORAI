"""Инварианты качества поиска по отчётам `eval_retrieval.py`.

Зачем отдельным скриптом: те же проверки раньше жили heredoc-ом внутри
`ci.yml`, то есть существовали только в CI — а CI их и не выполнял, потому что
корпуса КР в репозитории нет. Теперь это обычный скрипт: его можно запустить
локально после замера и он же вызывается из workflow, если замер есть.

Проверяются инварианты, а не абсолютный recall: абсолютные цифры зависят от
версии модели эмбеддингов, а ложный отказ на реальном клиническом вопросе и
пропуск вне-доменного вопроса — это безопасность, и они не должны «плыть».

Использование:
    RERANK_BACKEND=off python scripts/eval_retrieval.py --holdout --k 6 \
        --general-cap 2 --json eval_holdout.json
    RERANK_BACKEND=off python scripts/eval_retrieval.py \
        --golden data/eval/lor_retrieval_fresh.json --k 6 --general-cap 2 \
        --json eval_fresh.json
    python scripts/check_eval_invariants.py eval_holdout.json eval_fresh.json
"""
import json
import sys

# Порог recall ниже измеренного (1.9.0: hold-out 1.000, fresh 1.000) с запасом
# на смену версии модели. Ложные отказы и вне-доменный отсев — без запаса:
# это не «качество», а клиническая безопасность.
MIN_RECALL = 0.85


def check(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        report = json.load(fh)
    s = report["summary"]
    keys = ("recall_at_k", "protocol_and_section_at_k", "false_refusal_rate",
            "out_refusal_rate")
    print(path, {k: s.get(k) for k in keys})
    bad = []
    if s.get("false_refusal_rate", 1.0) > 0:
        bad.append(f"{path}: ложные отказы на in-domain вопросах")
    if s.get("out_refusal_rate", 0.0) < 1.0:
        bad.append(f"{path}: вне-доменный вопрос не отсечён")
    if s.get("recall_at_k", 0.0) < MIN_RECALL:
        bad.append(f"{path}: recall@k ниже {MIN_RECALL}")
    return bad


def main(argv: list[str]) -> int:
    if not argv:
        print("укажите один или несколько отчётов eval_retrieval.py --json")
        return 2
    problems: list[str] = []
    for path in argv:
        problems += check(path)
    if problems:
        print("НАРУШЕНИЯ: " + "; ".join(problems), file=sys.stderr)
        return 1
    print("инварианты соблюдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
