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

## Premium-аудит 2026-10-06 (PREMIUM_AUDIT_BRIEF.md)
- Бриф сохранён как PREMIUM_AUDIT_BRIEF.md. Отчёт: docs/PREMIUM_AUDIT_REPORT.md.
- Итог: 8.4/10, вердикт — готово с оговорками к внутреннему пилоту.
  Порог 8.5 выполнен в 4/7 применимых категориях (визуал 8.5, контент 9.0,
  перф 8.5, a11y 8.5); бренд/микро/прод — по 8.0 (нет иллюстратора,
  нет SSE-стриминга ответа, нет прогона на физическом устройстве).
- Слой поверх Excellence-наработок (фичи Excellence не тронуты — pages.tsx
  сохранён как есть): `src/styles.css` (токены 8pt, типошкала, тёмная тема),
  каркас App (шапка-бренд, навигация с активным пунктом, ErrorBoundary,
  офлайн-баннер, футер с версией 1.1.0, skip-link), ApiError с человеческими
  текстами по HTTP-статусам + таймаут 30с, favicon/title/meta.
- Проверки: `npm run build` чистый, vitest 2/2 (backend-проверки — из upstream).
- Flutter-пункты брифа — N/A для web-стека, зафиксированы честно в отчёте.

## Stack Reconciliation + PWA 2026-10-06 (итог 9.0/10, ✅ пилот)
- DECISIONS #25: расхождение «Flutter-план vs React-код» закрыто официально —
  стек web/PWA (PWA-обёртка: manifest + SW + install prompt), Flutter-пункты — N/A.
- Новое: `GET /chat/stream` (SSE: meta → tokens → done, PII/отказ сохранены),
  стрим-рендер чата с кареткой и кнопкой «Остановить», PWA-ассеты
  (иконки 192/512/180, sw.js с офлайном протоколов, offline.html),
  4 line-art SVG в 5 пустых состояниях, базовые стили нативных элементов.
- Проверки: backend pytest 59/59 (SSE-тесты + chroma-стаб), vitest 4/4,
  build чистый (JS 173 КБ/gzip 57 КБ), Lighthouse desktop: perf 1.0, a11y 0.94.
- Отчёт: docs/PREMIUM_AUDIT_REPORT.md (v2). Условие перед первым врачом:
  ручная установка PWA + офлайн-протокол на реальном Android (см. KNOWN_ISSUES).
