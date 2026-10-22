# LORAI — ассистент ЛОР-врача (strict RAG по клиническим рекомендациям)

Отвечает на вопросы по 22 клиническим рекомендациям Минздрава: находит нужный протокол
и нужный раздел, цитирует источник, проверяет числа в ответе и честно отказывается,
когда в корпусе нет ответа. Это справочный инструмент: **решение принимает врач**.

## Быстрый старт

```bash
cp .env.example .env          # LLM_PROVIDER=mock работает без ключа
scripts/run_local.sh          # backend :8000 + frontend :5173 (SQLite, локальные векторы)
# или
docker compose up --build
```

Переиндексация корпуса: `python scripts/ingest_pdf.py .` (22 КР уже загружены).
Документация API: http://localhost:8000/docs

## Что внутри

| Слой | Где |
|---|---|
| API (FastAPI, роутеры) | `backend/app/routers/` — `/v1/...` |
| Поиск: e5 + маршрутизация по разделам и нозологии + опц. реранкер | `backend/app/rag/` |
| Разбор и проверка схем (PASS/REVIEW/REJECT) | `backend/app/clinical/` |
| Ингест PDF → разделы → чанки | `backend/app/ingestion/` |
| БД (SQLite/Postgres) + векторный индекс | `backend/app/knowledge_base/` |
| UI (React + Vite) | `frontend/src/` |

Подробности: `docs/ARCHITECTURE.md`.

## Версионирование API

Канонические пути — `/v1/...` (только они попадают в OpenAPI). Пути без префикса
продолжают работать для уже установленных клиентов, но отдают `Deprecation: true` и
`Link` на `/v1`. `/health` — вне версий (docker healthcheck).

## Тесты

```bash
.venv/bin/python -m pytest -q --basetemp=.pytest-tmp                 # backend, полный набор
.venv/bin/python -m pytest -q -m "not slow" --basetemp=.pytest-tmp   # быстрый цикл
cd frontend && npm test && npm run build
```

`--basetemp` нужен только в песочнице, где запрещена запись в `/private/var/folders`.
Маркер `slow` — тесты, поднимающие модель эмбеддингов.

Актуальные цифры (1.10.0): backend 285 тестов (быстрый цикл `-m "not slow"` — 267),
frontend 39 тестов, сборка 162.08 kB / 53.79 kB gzip. Время прогона backend сильно
зависит от машины и прогрева кэша модели — на этой машине от 1.5 до 8 минут, поэтому
цифра в секундах здесь не фиксируется.

Frontend собирается только на Node из `.nvmrc` (24). На другой версии `vitest` и `vite` падают
с `Cannot find module @rollup/rollup-darwin-arm64` — это не поломка кода, а несовпадение
нативного бинарника rollup с платформой сборки `node_modules`. Проверка: `node -v` перед `npm test`.

## Замер качества, а не «на глаз»

```bash
python scripts/eval_retrieval.py --holdout --general-cap 2            # базовая линия
python scripts/eval_retrieval.py --holdout --general-cap 2 --rerank   # с реранкером
python scripts/eval_retrieval.py --golden data/eval/lor_retrieval_fresh.json --general-cap 2
```

Третий набор (`lor_retrieval_fresh.json`) — для проверок, которые не должны быть
in-sample: hold-out уже участвовал в разработке правил нозологии, golden — в
калибровке разделов.

Гейт целиком (оба набора + инварианты) — `scripts/check_retrieval_gate.sh`. В GitHub
Actions его нет: там нет корпуса КР (PDF не коммитятся), поэтому push-CI проверяет
код (backend, frontend, e2e на синтетике), а качество поиска — на машине с корпусом.

Текущие цифры и оговорки: `docs/RETRIEVAL_EVAL.md`. Включение реранкера —
`RERANK_BACKEND=cross` (по умолчанию выключен: модель ~700 МБ, +1 с на запрос).

## Что защищает от ошибки

- **Числа в ответе сверяются с источником** (`check_numbers`): «5 мг» не проходит при «500 мг».
- **Домен-гейт**: вопрос не про ЛОР — честный отказ, а не ответ по ближайшему протоколу.
- **Валидатор схем**: `PASS` только при полной схеме, `REVIEW` при диапазонах/нехватке полей,
  `REJECT` при нераспознанном препарате. Вердикт умеет только понижаться.
- **ПДн-фильтр** на входе и ретенция запросов (90 дней) / журнала (365).
- **Аудит действий** админа и врача, отзыв доступа в БД, лимит попыток входа.

## Документы

`docs/ARCHITECTURE.md` · `docs/ADMIN_GUIDE.md` · `docs/USER_GUIDE.md` ·
`docs/RETRIEVAL_EVAL.md` · `docs/DECISIONS.md` · `docs/AUDIT_2026-10-19.md` ·
`docs/KNOWN_ISSUES.md` · `docs/GO_LIVE_CHECKLIST.md` · `CHANGELOG.md`
