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
