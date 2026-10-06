# DECISIONS
6. Домен-гейт отказа (аудит-3): TF-IDF-скор слова «лечение» (0.16) пробивал порог 0.12 на чужих специальностях. Добавлен has_lor_signal (лексика+коды H/J): без ЛОР-сигнала — отказ независимо от скора. Тесты маскировались неверным 0.75 в .env.
7. Дедуп загрузок по source_file/title: повторный upload обновляет запись (тот же document_id), вернёт duplicate:true.
8. POST /search-protocol — детерминированный доступ к БД без LLM (llm_used:false), требование точности дозировок.
9. PATCH /admin/documents — ручная правка low-confidence записей только админом.
10. /history под JWT (история запросов — чувствительные данные).
11. МКБ-фильтры: АТХ/витамины/supplement-страницы/номенклатура услуг — не диагнозы; реальные S/B/A-коды травм/инфекций сохранены.
12. Полнотекстовое покрытие: чанки по всему тексту (не первые 6000), full_text cap 60k — дозы в конце документов (offset 29k/80k) находились вне индекса.
13. Кэш процесс-локальный TTL (256 записей, 300с): только session-less /chat и /search-protocol; запросы с session_id не кэшируются (follow-up зависит от истории диалога). Для горизонтального масштабирования нужен Redis (см. ROADMAP).
14. Feedback — только сбор (таблица feedback, голоса ±1): модель «на лету» не меняется; агрегаты в GET /admin/stats (пробелы базы = частые отказы → сигнал догрузить КР).
15. Mobile-нативные пункты Excellence 2/2.5 (виджеты, OCR, haptics, App Shortcuts) не реализованы: Flutter-приложения в репозитории нет (папка /mobile отсутствует, SDK нет) — перенесены в ROADMAP, web получил эквиваленты (быстрый поиск, кэш, skeleton-loaders, онбординг).
16. Red flags — статичная таблица (core/red_flags.py), не LLM: скрининг «не диагноз, а повод срочно к врачу»; подключён к /diff-diagnosis (аддитивное поле) + открытый POST /red-flags.
17. Калькуляторы Centor/McIsaac и PTA — чистые формулы (core/calculators.py), валидация входов (400 при мусоре); LLM запрещён (защита цифр, как решение №5 про дозы).
18. Избранное врача — таблица Favorite (user, doc_id); удаление только своё (remove_favorite сверяет user, чужое → 404); endpoints под JWT.
19. CI (Excellence-6): .github/workflows/ci.yml — backend (pytest, Python 3.11) + frontend (tsc, build); надёжность уже покрыта rate-limit slowapi на /chat и /admin/upload + детальным /health.
1. Threshold 0.75→0.12: TF-IDF fallback даёт низкие абсолютные скоры (релевант 0.23, нерелевант 0.08). Порог 0.12 разделяет классы. При переходе на embeddings вернуть 0.75 (настройка .env LLM_THRESHOLD).
2. Chroma optional + TF-IDF fallback: индексация работает без torch/CUDA из коробки.
3. MockLLM по умолчанию: end-to-end тест без ключа; замена — только .env.
4. SQLite по умолчанию: запуск без Docker врачу; Postgres — в compose.
5. Таблицы доз — только rule-based, не в LLM (защита цифр).
1. Threshold 0.75→0.12: TF-IDF fallback даёт низкие абсолютные скоры (релевант 0.23, нерелевант 0.08). Порог 0.12 разделяет классы. При переходе на embeddings вернуть 0.75 (настройка .env LLM_THRESHOLD).
2. Chroma optional + TF-IDF fallback: индексация работает без torch/CUDA из коробки.
3. MockLLM по умолчанию: end-to-end тест без ключа; замена — только .env.
4. SQLite по умолчанию: запуск без Docker врачу; Postgres — в compose.
5. Таблицы доз — только rule-based, не в LLM (защита цифр).

## #20 (2026-10-05, ROADMAP п.4): TF-IDF остаётся бэкендом по умолчанию
- Факт: Chroma 1.5.9 + дефолтный ONNX all-MiniLM-L6-v2 (en-модель) на русских КР даёт сжатые скоры 0.4–0.7 без разделения релевантных/нерелевантных; топ по «тризм» — Меньера вместо паратонзиллярного абсцесса. TF-IDF на тех же запросах точнее.
- Решение: `VECTOR_BACKEND=tfidf|chroma` (config.py + vector_store.py), default `tfidf`. Chroma включается явно и покрыта тестом. Путь к multilingual: `EMBEDDING_MODEL=intfloat/multilingual-e5-base` — требует torch/sentence-transformers, не ставился в сессии (тяжёлый).
- Побочка переиндексации: повторный ingest задвоил SQLite до 44 (document_id недетерминирован) — почищено до 22. ingest без --clean опасен повторами.

## #21 (2026-10-05): rank дифдиагностики — токенное совпадение
- Дефект: `rank` требовал точное вхождение целой фразы симптома; «тризм жевательных мышц» не совпал с текстом «тризм жевательной мускулатуры» → ranked пуст.
- Фикс: `_matches` — хватило половины значимых слов (len>=4). Тест `test_diff_rank_token_match_phrase_not_verbatim`. Live: тризм → паратонзиллярный абсцесс первым.

## #22 (2026-10-05, ROADMAP п.7): Docker — BLOCKED, нет CLI
- Факт: `docker` отсутствует в системе полностью (не только daemon off); brew/apt нет, установка Docker Desktop — вне сессии. docker-compose.yml в репо есть, `compose up` не проверялся.
- Решение: пункт остаётся BLOCKED до установки Docker Desktop пользователем; локальный запуск — через scripts/run_local.sh (проверен).

## #23 (2026-10-05, ROADMAP п.8): Real LLM — DONE via OpenRouter
- Факт: пользователь выдал OpenRouter-ключ. Код уже поддерживал переключение (.env: LLM_PROVIDER=openrouter, BASE_URL=https://openrouter.ai/api/v1, MODEL=openai/gpt-4o-mini). Ключ — только в локальном .env (gitignored, в коммиты не попадает).
- По пути найден и исправлен баг: /health проверял legacy OPENAI_API_KEY и всегда врал mock — теперь llm_mode берётся из settings (api:<provider>/mock). Тесты приколоты к mock через conftest (LLM_PROVIDER=mock), иначе прогоны ходили бы в сеть.
- Проверка live: in-data запрос → реальный ответ с цитатами (latency 6.6с, без MOCK), инфаркт → refused True. pytest 48/48 за 3.6с (mock, сеть не трогают).

## #24 (2026-10-05, ROADMAP п.5/6): OCR PARTIAL, Playwright DONE
- OCR: pdf_loader `_ocr_fallback` + pipeline `failed/needs_manual_review` + test_ocr.py (синтетический скан). Без tesseract сканы помечаются, а не теряются. Для текста нужен `brew install tesseract tesseract-lang`.
- Playwright: e2e.smoke.spec.ts 7/7 PASS против live :8000; e2e.ci.spec.ts 4/4 на синтетике (seed_synthetic_data.py); CI-job e2e в ci.yml. Спеки бьют по API (быстро, 590мс), не по UI-кликам — полный UI-coverage при наличии времени.

## #25 (2026-10-06, STACK RECONCILIATION): Flutter — нет, стек — web/PWA
- Дата: 2026-10-06. Обнаружено расхождение между запланированным Flutter-стеком и фактической реализацией на React.
- Факт: решений о Flutter в DECISIONS (#1–24) нет — Flutter существовал только в брифах (AGENT_BRIEF/EXCELLENCE/PREMIUM как mobile-цель), а код с самого начала писался на React+Vite + FastAPI. Расхождение «план vs код», а не «код vs код»: выкидывать нечего, переписывать нечего.
- Принято решение: PWA-обёртка текущего веб-приложения для Android, как наиболее быстрый путь к устанавливаемому мобильному опыту без потери уже выполненной работы (manifest + Service Worker + install prompt; офлайн-доступ к ранее просмотренным протоколам = аналог требования мобильного ТЗ).
- Все Flutter-специфичные пункты проверок (adaptive icon, splash-натив, go_router, haptics, APK-размер, WorkManager, TalkBack-натив) — N/A, стек — web/PWA. Если пилот покажет нужду в нативном ОС-уровне (биометрия ОС, фоновая синхронизация без браузера) — Flutter-AGENT_BRIEF.md поднимать отдельным проектом, не параллельно.
- Premium-аудит 8.4/10 (⚠️) → план закрытия: SSE-стриминг чата, SVG-иллюстрации пустых состояний, прогон на устройстве; цель 9.0+ без оговорок.
