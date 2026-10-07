# Результаты замеров поиска (JSON)

Получены `scripts/eval_retrieval.py` (ранжирование) и `scripts/eval_answers.py`
(ответ-уровень, реальные вызовы LLM; `--judge` — оценка ответа судьёй).
Методика, таблицы и оговорки: [docs/RETRIEVAL_EVAL.md](../RETRIEVAL_EVAL.md).

## Ранжирование

| Файл | Датасет / корпус |
|---|---|
| `old-final-tfidf.json`, `old-final-emb.json` | golden, ПРЕЖНИЙ корпус (1599 чанков, 84 % дублей `general`) — база «до» |
| `final-tfidf-routing.json`, `final-emb-routing.json` | golden, корпус 1899 чанков (первая пересборка) |
| `final2-golden-emb.json` | golden (in-sample), финальный корпус 1084 чанка |
| `holdout-final-tfidf.json`, `holdout-final-embeddings.json` | **hold-out**, финальный корпус |
| `final2-holdout-emb.json` | **hold-out, рабочая конфигурация** (порог 0.75) |
| `holdout-emb-w0.json` / `holdout-emb-w0.15.json` | hold-out, сравнение без/с гибридным ранжированием |
| `holdout-strict-embeddings.json`, `holdout-clean-emb.json` | hold-out на промежуточных корпусах (строгие метки; +фильтр мусора) |

## Ответ-уровень

| Файл | Что это |
|---|---|
| `answers-original.json` | прежний корпус (TF-IDF), 8 вопросов |
| `answers-new-tfidf.json`, `answers-new-embeddings.json` | корпус 1899, 12 вопросов |
| `holdout-answers-judge.json` | hold-out, свободные метки + LLM-судья |
| `holdout-answers-strict.json`, `holdout-answers-clean.json` | hold-out, промежуточные корпуса |
| `holdout-answers-shipped.json` | **hold-out, рабочая конфигурация, с судьёй** |

Золотой набор: `data/eval/lor_retrieval_golden.json` (настройка),
hold-out: `data/eval/lor_retrieval_holdout.json` (проверка обобщения).
