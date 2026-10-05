# AUDIT_REPORT — независимая проверка LORAI (2026-10-05, итерация 3)

Метод: реальный запуск кода/тестов/HTTP, не чтение «по диагонали».
Стек проверки: backend pytest 21/21, frontend vitest 2/2, live HTTP :8000, SQL, векторы.

## БЛОК 1. Инфраструктура — все PASS
- [PASS] `docker-compose config` валиден. `up --build` невозможен: Docker daemon выключен (см. KNOWN_ISSUES).
- [PASS] `run_local` fallback: SQLite + TF-IDF без Docker — сервер :8000 жив, зависимости опциональны (chromadb/sentence-transformers отсутствуют → fallback работает).
- [PASS] `.env.example` покрывает 100% `settings.*` (12/12, проверено скриптом, расхождений нет).
- [PASS] health-check frontend/backend отвечают. README шаги verified.
- [FIXED] `.env`/`.env.example` LLM_THRESHOLD был 0.75 против задокументированных 0.12 → выставлен 0.12 с комментарием.

## БЛОК 2. Ingestion — PASS после 5 фиксов
- [PASS] `ingest_pdf.py` на 22 реальных PDF без падений.
- [FIXED] Пустой/битый файл ронял `fitz.open` исключением → `load_pages` теперь всегда возвращает структуру, статус failed + needs_review.
- [FIXED] Нестандартные заголовки тихо теряли текст (needs_review=False) → флаг при <2 найденных секций.
- [FIXED] Ложные МКБ: витамин B12, АТХ (D08AJ, «Код АТХ: N02», АТХ-N06, (R06:…)), supplement-страницы (S55/S79/S22/S74/S88/E10/E47), номенклатура услуг (A23.25.001) → контекстные фильтры + 12 asserts в тестах.
- [FIXED] Покрытие: доза на offset 28953/80495 не попадала ни в SQL (cap 20k), ни в векторы (первые 6000) → чанкинг всего текста (405→1598 чанков), full_text cap 60k. Сверка 8/8 чисел дословно.
- [PASS] Таблиц pdfplumber в корпусе нет (дозы в тексте) — table_parser корректно пуст, числа идут из текста без LLM-переписывания.
- [PASS] Чанки несут document_id/section/page_range (проверено 3 случайных).

## БЛОК 3. База знаний — PASS
- [PASS] SQL: 22 документа, 0 needs_review. Векторы: 1598 чанков, пересобраны начисто.
- [PASS] `POST /admin/upload-pdf` (алиас к /admin/upload) через HTTP: приём, ответ, появление в БД.
- [FIXED] Повторная загрузка плодила дубликаты (uuid) → дедуп по source_file/title, `duplicate:true`. Тест.
- [PASS] `alembic upgrade head` на чистой БД: documents/query_log/favorites + версия.

## БЛОК 4. RAG / anti-hallucination — КРИТИЧЕСКИЙ, был провал, исправлен
- [FAIL→FIXED] «Перелом лучевой кости» отвечал MOCK-текстом (refused=False): TF-IDF-скор 0.163 > порога 0.12 за счёт слова «лечение». Причина замаскирована: тесты проходили только из-за неверного порога 0.75 в .env.
- Фикс: домен-гейт `has_lor_signal()` (ЛОР-лексика + коды H/J) — вопрос без ЛОР-сигнала → честный отказ независимо от скора. Live: перелом→refused=True, отит→ответ с 6 источниками.
- [PASS] Пограничные: «отит и насморк?» — ответ; «лечение вообще» — отказ; «дозировка для уха» (vague) — безопасный отказ.
- [PASS] `check_numbers`: несовпадение (875 vs 500 мг) → пометка «требует проверки».
- [PASS] MockLLM без ключа; OpenAICompatible с фиктивным ключом падает только на сети (ConnectError), абстракция цела.
- [FIXED] `POST /search-protocol` отсутствовал → добавлен (DB-only, `llm_used:false`, поиск по q/нозологии/МКБ/симптому). Поиск по симптому починен (расширен haystack).

## БЛОК 5. Модули — все PASS реальными вызовами
Чат, поиск ×3 (нозология/МКБ/симптом), дозы (20кг×40=800; педиатр. 12×40=480; cap 3000), дифдиагноз (отит score 1.0), чек-лист (5 блоков, печать через window.print), шаблоны (реальные данные), referral, история (auth, персист), админка (upload, статусы, список, PATCH low-confidence — [FIXED] эндпоинта не было, добавлен `PATCH /admin/documents/{id}`, врач→403).

## БЛОК 6. Безопасность — PASS
401 без токена; 403 врач→admin (списки, upload, patch); rate-limit эмпирически (40 параллельных → 14×429); .exe→400 «Не похоже на PDF»; ПДн-фильтр; PII-предупреждение в UI чата [FIXED].

## БЛОК 7. UX — PASS с оговорками
Дисклеймер-баннер везде; источники в чате рендерятся карточками [FIXED]; build без ошибок; тёмная тема НЕ заявлена (N/A); адаптивность базовая. Web-клиент остаётся до Flutter-фазы.

## БЛОК 8. Тесты — PASS
pytest 21/21 (отказ, домен-гейт, роли, дедуп, дозы×3, МКБ-артефакты, пустой файл, секции); vitest 2/2.

## БЛОК 9. Документация — обновлена
ARCHITECTURE (новые эндпоинты/гейт), DECISIONS (+7), KNOWN_ISSUES (честно), FINAL_REPORT (без преувеличений — переписан ниже).

## БЛОК 10. E2E — 7/7 PASS
upload→search→chat(6 источников)→dosage 900мг→checklist→template→history; мусор удалён.

## Остаточный техдолг (не блокеры)
- VectorStore без delete: удалённые документы оставляют чанки (добавить tombstone/GC).
- search_protocols — full scan 22×60k (при росте корпуса нужен FTS-индекс).
- Threshold 0.12 валиден только для TF-IDF; при embeddings вернуть 0.75.

# АУДИТ-4 (2026-10-05, живой стенд :8000, 22 docs / 1599 chunks)
## Блоки 1–3 — PASS с замечаниями
1. Окружение: /health ok (mock, 22/1599); Docker daemon OFF — compose не поднят (KNOWN_ISSUES); run_local.sh/.bat в scripts/; .env.example покрывает все settings.
2. Данные: ингест 22/22; OCR PARTIAL (tesseract нет, pipeline честно маркирует failed + needs_manual_review).
3. Миграции: создан 0002_feedback (таблицы documents/feedback/query_log/favorites upgrade 0001→head ok); login admin/doctor ok.
## Блок 4 — PASS + 1 дефект (исправлен)
In-data отвечает с источниками; инфаркт → честный отказ. Дефект: вопрос о дозе без слов-нозологий отказывал (score 0.146, в LOR_MARKERS не было лекарственной лексики) → исправлено anti_hallucination.py (лекарства + доза/дозировка/мг-кг/ребёнок/детск/педиатр), live: доза→needs_clarification, инфаркт→отказ. Регресс-тест test_audit4_dosage_without_nosology_clarifies. Попутно вскрыта порядковая зависимость тестов (сид не индексировался в VectorStore) → conftest индексирует сид.
## Блок 5 — PASS
Все модули 200: dosage/checklist/diff-diagnosis/referral-check/history/templates/discharge/related/contradictions(auth)/drug-check(auth)/favorites/stats/centor/pta. /search-protocol llm_used=False всегда (обхода LLM нет).
## Блок 6 — PASS
401 без токена, 403 врач→/admin/*, .exe-под-PDF → чистая 400; прод не загрязнён (upload настоящего файла пропущен сознательно — нет DELETE документов).
## Блок 7/10/11 mobile — BLOCKED (нет Flutter SDK, DECISIONS #15)
## Блок 8 — BLOCKED (Playwright-браузеры не ставились)
## Дополнительно: rate-limit 30×200+429 ok; дисклеймер во всех ответах; ПДн-баннер в чате; README точен.
## Итог: pytest 45/45, tsc clean, vitest 2/2, прод 22 docs цел.
