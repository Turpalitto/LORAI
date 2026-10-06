# GO-LIVE CHECKLIST — запуск пилота ЛОРАИ

## A. Выполнено агентом автоматически ✅
- [x] PWA-обёртка: manifest, иконки 192/512/180, Service Worker (shell + SWR протоколов + offline), install prompt, offline.html
- [x] SSE-стрим чата: `GET /chat/stream` (meta → token → [corrected] → done), стрим-рендер с кареткой/стопом, фолбэк на POST /chat
- [x] True token-stream готовности: `BaseLLMClient.stream()` + реализация в OpenAICompatibleClient; с mock — нарезка (фронт не меняется при переключении)
- [x] `scripts/verify_llm_connection.py` — сухой прогон ключа (auth, ответ, SSE-формат, без печати ключа)
- [x] Admin-upload end-to-end: статусы/уверенность/duplicate в ответе, UI-цикл «загрузка → готово/ошибка с причиной → проверить в поиске», тест `test_upload_returns_lifecycle_fields_and_searchable`
- [x] Кнопка «Сообщить о проблеме» (авто-контекст: вопрос/ответ/score/сессия, без ПДн) → POST /feedback
- [x] `docs/PILOT_PLAN.md` (метрики, ритм, критерии перехода/стопа), `docs/DEVICE_TEST_PROTOCOL.md` (15 мин)
- [x] Тесты: backend 61/61, frontend vitest 4/4, build чистый; Lighthouse desktop: perf 1.0 / a11y 0.94

## B. Требует одного ручного действия пользователя ⬜
- [ ] **LLM-ключ**: в `.env` вписать `LLM_PROVIDER=openrouter` (или openai),
  `LLM_API_KEY=<ключ>`, `LLM_MODEL=openai/gpt-4o-mini` (или своя модель),
  при openrouter — `LLM_BASE_URL=https://openrouter.ai/api/v1`. Перезапустить backend
  (`scripts/run_local.sh` или свой процесс). Проверить: `python scripts/verify_llm_connection.py`
  → код 0. Затем smoke: вопрос в чате → ответ идёт потоком; инфаркт → честный отказ.
- [ ] **Реальные PDF**: передать файлы клинических рекомендаций (Минздрав) любым способом.
  Дальше: `python scripts/ingest_pdf.py <папка>` → сверка 10–15% полей с оригиналом
  (дозы, МКБ-10, разделы) → разбор `needs_manual_review`. ⬅️ ОТКРЫТЫЙ ВОПРОС №1 (см. ниже)
- [ ] **DEVICE_TEST_PROTOCOL**: пройти 15-минутный сценарий на 2 телефонах (раздел D — минимум).
- [ ] **Доступ**: поднять frontend+backend на адресе, доступном телефонам врачей
  (https или http в Wi-Fi клиники); вписать URL фронта в `LORAI_ALLOWED_ORIGINS` backend.

## C. Рекомендовано перед масштабированием за пределы пилота
- [ ] Admin-upload: заменить sync-обработку на фоновую очередь при PDF >50 МБ / десятках файлов
- [ ] Экспорт логов для техподдержки (кнопка в админке)
- [ ] DEPLOY_GUIDE.md (docker compose для клиники) вместо разрозненных инструкций
- [ ] Полный офлайн-режим (предзагрузка всех КР в SW-кэш при установке)
- [ ] Нативная эскалация только по итогам пилота (биометрия ОС, фон — см. DECISIONS #25)

## Открытые вопросы к пользователю
1. **Реальные PDF клинических рекомендаций** — единственный блокер валидации экстракции.
   Без них: синтетика покрыта тестами, но `extraction_confidence` на реальной вёрстке
   Минздрава не измерен. Пришлите 2–3 PDF для начала (можно самые частые нозологии приёма).
2. LLM-ключ — в этой среде ключа нет (mock); включить по инструкции выше (5 минут).
