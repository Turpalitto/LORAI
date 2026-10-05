# CHANGELOG — LORAI

## [Unreleased] — сессия Excellence 2026-10-05 (продолжение, незакоммичено)

### Техдолг аудита (закрыт)
- `VectorStore.delete_by_document()` (fallback + chroma) + вызов при дедуп-загрузке.
- TF-IDF: предвычисленный индекс (`_index_all`) вместо full-scan на запрос (~85мс → ~13мс).
- Фикс буста пустой подстроки; ранний отказ на пустой запрос в генераторе.
- `backend/tests/conftest.py`: изоляция тестов (tmp `DATABASE_URL`/`CHROMA_DIR`, `LORAI_TESTING=1`), детерминированный сид протокола H66.9.

### Excellence-1: интеллектуальный слой RAG
- `rag/clarify.py` — уточняющие вопросы (вес/возраст при дозировках).
- `rag/sessions.py` — память диалога, раскрытие follow-up.
- `features/drug_interactions.py` + `POST /drug-check` — только цитаты из протоколов, честный вердикт при отсутствии данных.
- `features/nosology_graph.py` + `GET /protocols/{id}/related`, `GET /contradictions` — связанные протоколы, пары с расходящимися назначениями.
- `differential_diagnosis.py` — IDF-взвешивание, `why_first`/`key_signs`/`explanation`.
- Генератор: `source_map`, `doc_count`, `session_id`, `needs_clarification` (после гейта отказа).

### Excellence-2/2.5/3: скорость + UX-полиск web (mobile-натив — см. ROADMAP)
- `core/cache.py` — TTL-кэш (256/300с) + rolling latency (200).
- Детальный `/health` (документы, чанки, кэш, latency); `cached`/`latency_ms` в `/chat` (только без `session_id`) и `/search-protocol`.
- Таблица `Feedback` + `POST /feedback`, `GET /admin/stats` (запросы/отказы/пробелы базы/оценки).
- Frontend: онбординг, бейдж уверенности, skeleton/error/empty, `session_id` в чате, 👍/👎, похожие протоколы, print-CSS чек-листа, аналитика и противоречия в админке.

### Excellence-4–6: аналитика, клиника, надёжность
- `POST /red-flags` + `core/red_flags.py` (8 ЛОР-сигналов, keyword-scan, не диагноз); баннер в дифдиагностике.
- `POST /calculators/centor|pta` + `core/calculators.py` (Centor/McIsaac clamp 0–5, PTA 0.5/1/2/4 кГц + градации ВОЗ, +disclaimer); страница «Калькуляторы».
- Избранное врача: `DELETE /favorites/{id}` (удаление только своё), ⭐ в поиске протоколов.
- `.github/workflows/ci.yml` (pytest + tsc + build).

### Проверки сессии
- pytest 44/44 (новые `test_techdebt` 3 шт, `test_excellence1` 7 шт, `test_excellence2` 5 шт, `test_excellence46` 8 шт), tsc clean, vite build ok, vitest 2/2, live-smoke `:8000`.
- Прод-БД: 22 документа / 1599 чанков, данные целы (md5-контроль до/после прогонов).

## audit-3 — 2026-10-05 (коммит 747c973)
- 13 дефектов живой проверкой (см. `docs/AUDIT_REPORT.md`): домен-гейт отказа, порог 0.75→0.12, чистка МКБ-артефактов, покрытие чанками всего текста, дедуп, `/search-protocol`, PATCH документов, роли, auth `/history`, PII-баннер.
- pytest 21/21, e2e 7/7. Векторы пересобраны (22 документа / 1598 чанков).
