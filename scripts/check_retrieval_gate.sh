#!/usr/bin/env bash
# Гейт качества поиска: два замера + инварианты.
#
# Запускается там, где лежит корпус клинических рекомендаций (папка
# «лор клинреки» или data/raw_pdfs). В GitHub Actions корпуса нет — PDF не
# коммитятся, — поэтому гейт не в push-CI, а здесь (см. KNOWN_ISSUES, 1.10.0).
#
#   scripts/check_retrieval_gate.sh
#   PYTHON=/path/to/python scripts/check_retrieval_gate.sh
#
# Реранкер выключен явно: цифры в docs/RETRIEVAL_EVAL.md измерены с ним off,
# и «случайно включённый» реранкер меняет вывод, не меняя код.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python}
export RERANK_BACKEND=${RERANK_BACKEND:-off}
export VECTOR_BACKEND=${VECTOR_BACKEND:-embeddings}

echo "== hold-out =="
"$PYTHON" scripts/eval_retrieval.py --holdout --k 6 --general-cap 2 --json eval_holdout.json

echo "== свежий набор (не in-sample для правил нозологии) =="
"$PYTHON" scripts/eval_retrieval.py \
  --golden data/eval/lor_retrieval_fresh.json --k 6 --general-cap 2 --json eval_fresh.json

echo "== инварианты =="
"$PYTHON" scripts/check_eval_invariants.py eval_holdout.json eval_fresh.json
