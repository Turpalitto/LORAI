# FINAL_REPORT — LORAI (2026-10-05, после независимого аудита-3)

База: 22 PDF клинических рекомендаций, 1598 чанков, коды МКБ переизвлечены и очищены от артефактов.

## Статус проверок (всё выполнено реальным запуском)
- Backend pytest 21/21, frontend vitest 2/2, `npm run build` ок.
- Live :8000: /health, /protocols, /chat (ответ с 6 источниками + честный отказ на чужой специальности),
  /search-protocol (DB-only), /dosage (800/480/3000 мг), /diff-diagnosis, /checklist, /templates,
  /referral-check, /history (JWT), /favorites, PATCH /admin/documents (админ).
- E2E 7/7: upload → search → chat → dosage → checklist → template → history.
- Безопасность: 401 без токена, 403 врач→admin, 429 при бурсте, .exe→400, ПДн-фильтр + PII-баннер.
- `alembic upgrade head` на чистой БД ок. `docker compose config` валиден; daemon выключен.
- Дословность чисел: 8/8 дозировок из PDF совпадают в БД/чанках.

## Что исправил аудит-3 (13 пунктов, см. docs/AUDIT_REPORT.md)
Критический провал честного отказа (TF-IDF-скор «лечения» пробивал порог) → домен-гейт;
порог .env 0.75→0.12; ложные МКБ (B12/АТХ/supplement/услуги); покрытие чанками всего текста;
дедуп загрузок; новые эндпоинты /search-protocol, /admin/upload-pdf, PATCH документов;
роли и auth; UI чата (PII-баннер, карточки источников).

## Пользователю
- Backend жив на :8000 (запущен скрыто). Frontend: `npm run dev` в frontend/ → :5173.
- Real LLM: .env → LLM_PROVIDER=openai + LLM_API_KEY. Порог 0.12 (TF-IDF); с embeddings — 0.75.
- Новые PDF → `python scripts/ingest_pdf.py .` (дедуп включён).
- Дальше по плану: Flutter-пивот (AGENT_BRIEF.md) — блокер: установить Flutter 3.x + Android SDK.

## Сессия Excellence (2026-10-05, продолжение — live-проверка, незакоммичено)

База: 22 документа / 1599 чанков, данные целы (md5-контроль до/после всех прогонов).

- Техдолг закрыт: `delete_by_document`, TF-IDF-индекс (~85мс → ~13мс), фикс пустого буста/запроса, изоляция тестов (`conftest.py`: tmp БД, `LORAI_TESTING=1`).
- Excellence-1: уточняющие вопросы, память диалога, `/drug-check`, `/protocols/{id}/related`, `/contradictions`, IDF-дифдиагностика с `why_first`, `source_map`/`needs_clarification` в `/chat`.
- Excellence-2/2.5/3 (web-срез; mobile-натив невозможен — `/mobile` отсутствует, Flutter SDK нет): TTL-кэш + `cached`/`latency_ms`, детальный `/health`, `/feedback` + `/admin/stats`, UX-полиск (онбординг, бейдж уверенности, skeleton/error/empty, 👍/👎, print-CSS).
- Excellence-4–6: `/red-flags` (8 сигналов) + баннер в дифдиагностике, `/calculators/centor|pta` + страница «Калькуляторы», `DELETE /favorites/{id}`, CI workflow.
- Проверки: pytest 44/44, tsc clean, vite build ok (163KB), vitest 2/2, live-smoke всех новых роутов на :8000.
- Детали: CHANGELOG.md, ROADMAP.md, docs/DECISIONS.md (#13–19), docs/PROGRESS_LOG.md.
