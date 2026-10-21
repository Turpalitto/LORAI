# AUTONOMOUS BUILD BRIEF
# ИИ-ассистент врача-оториноларинголога — серверный backend + кроссплатформенное
# мобильное приложение (Flutter, фокус Android, внутреннее распространение)

================================================================
РЕЖИМ РАБОТЫ: ПОЛНАЯ АВТОНОМИЯ
================================================================

Ты — автономный staff-инженер с экспертизой в MedTech, обработке PDF/NLP,
RAG-архитектурах, LLM-интеграции и кроссплатформенной мобильной разработке
(Flutter). Доведи проект от нуля до полностью работающего продукта за одну
непрерывную сессию, без остановок и без запроса подтверждений у пользователя.

Правила принятия решений в условиях неопределённости — как и ранее: при развилке
выбирай самый надёжный проверенный вариант, фиксируй в `docs/DECISIONS.md`,
иди дальше. Если нет реальных PDF — тестируй на синтетических данных. Если
нет LLM-ключа — используй `MockLLMClient`. Тесты не проходят — чини сам,
максимум 10 итераций, иначе документируй в `docs/KNOWN_ISSUES.md` и двигайся
дальше. По завершении всех этапов — `FINAL_REPORT.md`.

НЕ ЗАДАВАЙ ВОПРОСОВ. Решения фиксируй в `docs/ASSUMPTIONS.md`.

================================================================
АРХИТЕКТУРА ПРОДУКТА (клиент-серверная)
================================================================

Это НЕ автономное мобильное приложение с локальной БД клинрекомендаций — это
клиент к единому серверу клиники/организации. Один backend-сервер (развёрнутый
в клинике или в облаке клиники) хранит базу знаний (клинические рекомендации),
обслуживает всех врачей клиники одновременно через мобильные приложения на
их телефонах/планшетах.

Преимущества такого подхода (зафиксируй как обоснование в DECISIONS.md):
- Единая, централизованно обновляемая база клинических рекомендаций — админ
  загружает PDF один раз на сервер, все врачи сразу получают доступ
- Телефон врача не хранит полную медицинскую базу знаний локально (безопаснее)
- Офлайн-режим реализуется через локальный кэш последних использованных данных,
  а не полное дублирование базы

================================================================
ЦЕЛЬ ПРОДУКТА
================================================================

1. **Backend** (без изменений по сути от исходной серверной архитектуры):
   извлекает структурированные данные из PDF клинических рекомендаций по ЛОР,
   строит гибридную базу знаний (PostgreSQL + векторная БД), предоставляет REST API.
2. **Мобильное приложение (Flutter)**: кроссплатформенный клиент (приоритет Android,
   iOS-совместимость закладывается архитектурно, но не тестируется в первом релизе),
   предоставляющий врачу все инструменты умного помощника в удобном мобильном
   формате, с офлайн-кэшем часто используемых протоколов.
3. Распространение приложения — **внутреннее**: сборка APK для прямой установки
   сотрудникам клиники и/или через Firebase App Distribution (без публикации
   в Google Play на данном этапе — оставь архитектуру готовой к публикации
   в будущем, но не трать время на Play Store compliance сейчас).
4. В конце пользователь впишет реальный LLM API-ключ в `.env` сервера.

================================================================
ЖЁСТКИЕ ПРИНЦИПЫ МЕДИЦИНСКОГО ДОМЕНА (без изменений)
================================================================

- Strict RAG: ответы только на основе базы знаний, честный отказ при отсутствии
  данных (порог релевантности, по умолчанию 0.75)
- Трассируемость: каждый тезис — ссылка [Документ, Раздел, Стр.]
- Дисклеймер на каждом экране приложения: "Инструмент носит вспомогательный
  справочный характер. Решение принимает врач."
- Запрет на ввод персональных данных пациента — предупреждение перед полем чата
- Версионность клинических рекомендаций
- Локальное хранение на сервере, внешние вызовы только к LLM API

================================================================
ТЕХНИЧЕСКИЙ СТЕК
================================================================

## Backend (сервер — без изменений от исходного плана)
Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 + Alembic, PostgreSQL 16
(с fallback на SQLite для локального теста), PyMuPDF + pdfplumber + pytesseract
для извлечения PDF, ChromaDB для векторного поиска, sentence-transformers
(multilingual-e5-base) для embeddings, собственный лёгкий RAG-слой,
абстрактный `BaseLLMClient` (OpenAI-совместимый + Mock).
→ ВСЯ логика извлечения PDF, структурирования, RAG, anti-hallucination,
функциональных модулей backend — реализуется ТОЧНО так же, как описано в
полной спецификации ниже (раздел "BACKEND SPEC").

## Мобильное приложение
- **Flutter 3.x (Dart 3.x)** — кроссплатформенность на будущее (iOS),
  сборка под Android как основной таргет сейчас
- **State management**: Riverpod (предпочтительно) — чистая архитектура,
  тестируемость
- **Навигация**: go_router
- **Сетевой слой**: Dio (interceptors для JWT, retry policy, логирование),
  типизация через `dio` + `json_serializable`
- **Локальное хранилище**:
  - `drift` (SQLite-обёртка) — кэш структурированных протоколов для офлайн-доступа
  - `flutter_secure_storage` — хранение JWT-токена и чувствительных настроек
    (обязательно, не SharedPreferences для токенов!)
  - `hive` — быстрый key-value кэш (история запросов, избранное, настройки UI)
- **Авторизация устройства**: `local_auth` — биометрическая блокировка приложения
  (Face ID/отпечаток/PIN) перед каждым открытием — обязательно для мед. приложения
- **Голосовой ввод**: `speech_to_text` (нативная интеграция Android Speech API)
- **PDF-генерация/просмотр** (чек-листы, заключения): `pdf` + `printing` пакеты
- **Фоновая синхронизация кэша**: `workmanager`
- **Уведомления** (для follow-up/напоминаний в будущем): `flutter_local_notifications`
- **Сборка и распространение**: `flutter build apk --release`; Firebase App Distribution
  для внутренней раздачи тестовых сборок сотрудникам клиники
- **Тестирование**: `flutter_test` (unit/widget), `integration_test` (e2e
  на эмуляторе/устройстве), `mocktail` для моков

================================================================
СТРУКТУРА РЕПОЗИТОРИЯ
================================================================
/backend (серверная спецификация без изменений)
/app
/api
/core
/ingestion
/knowledge_base
/rag
/llm_clients
/features
main.py
/tests
alembic/
requirements.txt
Dockerfile

/mobile (Flutter-приложение)
/lib
/core — api_client.dart (Dio-клиент, interceptors), secure_storage.dart,
app_config.dart (dev/staging/prod URL), biometric_gate.dart, theme.dart
/data — models (зеркалят backend Pydantic-схемы), repositories (API + кэш,
"сначала кэш, потом сеть, обновить кэш"), local_db (drift: кэш протоколов, история)
/features — auth, chat, protocol_search, dosage_calculator, differential_diagnosis,
checklist_generator, report_templates, referral_criteria, history, admin, settings
(каждый: presentation / application (riverpod) / domain)
/shared/widgets — SourceCitationCard, ConfidenceBadge, DisclaimerBanner, EmptyState, ErrorView
main.dart, router.dart
/test, /integration_test, pubspec.yaml, android/, ios/ (минимум, не тестируется)

/data (на сервере: raw_pdfs, processed, vector_store)
/docs
/scripts
docker-compose.yml (только backend-сервисы: backend, postgres)
.env.example
README.md
FINAL_REPORT.md

================================================================
BACKEND SPEC (реализуется полностью)
================================================================

1. **Схема клинической рекомендации** (строгий JSON: definition,
   etiology_epidemiology, classification, diagnostics {complaints, anamnesis,
   physical_exam, lab_tests, instrumental_tests, differential_diagnosis},
   treatment {conservative[] с dosage_adult/dosage_pediatric/dosage_by_weight_formula,
   surgical[], indications_for_hospitalization[]}, complications, prevention,
   prognosis, referral_criteria, follow_up; плюс icd10_codes, approval_year,
   source_pages, extraction_confidence, needs_manual_review).

2. **Пайплайн извлечения PDF**: PyMuPDF постранично → OCR fallback для сканов →
   разбиение на разделы (regex + fuzzy заголовков рубрикатора) → детерминированный
   парсинг таблиц дозировок (pdfplumber, без LLM) → regex-МКБ-10 с кросс-валидацией
   по офлайн-справочнику H60-H95/J00-J39/C30-C32 → LLM-структурирование
   («ничего не придумывай, при отсутствии — null») → Pydantic-валидация →
   чанкинг (300-500 токенов, overlap 50, метаданные document_id/section/page_range/
   nosology/icd10) → ChromaDB + PostgreSQL. CLI: `scripts/ingest_pdf.py`.
   Без PDF от пользователя — 2-3 синтетических примера.

3. **RAG-движок**: intent → retrieval top-k с metadata-фильтрами → порог
   (отказ при score < threshold, без LLM) → жёсткий системный промт (только контекст,
   ссылка на источник, запрет домысливания) → генерация → сверка чисел/кодов
   с чанками → пометка «требует проверки». Прямой путь `/search-protocol` — без LLM.

4. **LLM-клиент**: `BaseLLMClient`, `OpenAICompatibleClient` (.env: LLM_PROVIDER,
   LLM_API_KEY, LLM_MODEL, LLM_BASE_URL) + `MockLLMClient`.

5. **REST API** (версия `/api/v1/...`, единый формат `{data, error, meta}`):
   `POST /auth/login`, `POST /auth/refresh`, `POST /chat`, `POST /search-protocol`,
   `GET /protocols/{id}`, `GET /protocols?icd10=&nosology=&query=`,
   `POST /tools/dosage-calculator`, `POST /tools/differential-diagnosis`,
   `POST /tools/checklist-generator` (backend отдаёт данные, PDF рендерит приложение),
   `POST /tools/report-template`, `POST /tools/referral-check`,
   `GET /history`, `POST /history`, `POST /admin/upload-pdf`,
   `GET /admin/documents`, `GET /admin/documents/{id}/status`, `GET /health`
   (детальная проверка БД/векторов/LLM).

6. **Безопасность backend**: JWT, роли врач/администратор, rate limiting,
   валидация PDF, CORS под мобильный клиент (любой origin для native, JWT на
   каждом защищённом эндпоинте).

================================================================
MOBILE APP SPEC (Flutter)
================================================================

### Архитектура
Clean Architecture по фичам (feature-first), Riverpod, repository pattern:
**"cache-first with background refresh"** — сначала Drift-кэш (мгновенно),
параллельно сеть, обновление кэша и UI (stream-based providers).

### Экраны (1:1 с модулями backend)
1. **Splash + Biometric Gate** — токен, биометрия при запуске/возврате из фона (по умолчанию вкл)
2. **Login** — логин/пароль, JWT в secure_storage
3. **Dashboard** — плитки модулей, глобальный поиск, последние протоколы из кэша
4. **Chat** — сообщения, «печатает», карточки источников со страницами, голосовой ввод,
   one-time dialog про запрет ПДн, контекст диалога
5. **Protocol Search** — нозология/МКБ-10/симптом, карточка с якорной навигацией,
   confidence, офлайн из кэша
6. **Dosage Calculator** — форма (препарат, вес/возраст) → расчёт + формула + источник
7. **Differential Diagnosis** — симптомы чипами с автокомплитом → ранжированный список с %
8. **Checklist Generator** — чекбоксы на приёме → PDF-экспорт/печать
9. **Report Templates** — автозаполнение → редактирование → PDF/буфер
10. **Referral Criteria Check** — чек-лист критериев по нозологии
11. **History** — запросы и поиски, повтор/избранное
12. **Admin Panel** (только administrator) — загрузка PDF (`file_picker` или URL),
    статусы, pull-to-refresh
13. **Settings** — URL сервера, биометрия, тема, версия, экспорт логов

### Офлайн-режим (обязательно)
- Drift: `cached_protocols`, `cached_history`, `favorites`
- Открытый протокол кэшируется целиком на 30 дней (TTL настраивается), доступен без сети
- Индикатор «офлайн / кэшированные данные»; чат и дифдиагностика офлайн недоступны
  с понятным сообщением, поиск по кэшу работает

### Безопасность приложения
- JWT только в `flutter_secure_storage`; биометрия (`local_auth`); автоблокировка
  после N минут неактивности; certificate pinning (или в KNOWN_ISSUES);
  обфускация (`--obfuscate --split-debug-info`); `FLAG_SECURE` на всех экранах

### UI/UX
- Material 3, медицинская палитра, тёмная/светлая темы
- Источники + дисклеймер у ответов; пустые состояния, ошибки сети, skeleton-loaders
- Accessibility: увеличенный шрифт не ломает вёрстку

================================================================
ПОСЛЕДОВАТЕЛЬНОСТЬ ВЫПОЛНЕНИЯ (ЭТАПЫ 0-14)
================================================================
0 — Монорепозиторий (/backend, /mobile), compose, .env.example, Flutter-скелет, README.
1 — Backend: PDF-пайплайн на синтетике. 2 — Backend: БЗ + миграции + /admin/upload-pdf.
3 — Backend: RAG + MockLLM + anti-hallucination. 4 — Backend: все REST endpoints + pytest + /docs.
5 — Mobile: проект (Riverpod, go_router, Dio, Drift, secure_storage, local_auth), Dart-модели = backend DTO.
6 — Mobile: Auth, Dashboard, Protocol Search (офлайн-кэш) — ядро, безупречно.
7 — Mobile: Chat (источники, голос, контекст), Dosage, DiffDx.
8 — Mobile: Checklist, Templates, Referral (PDF через `pdf`), History, Favorites.
9 — Mobile: Admin (загрузка с устройства), Settings (URL, биометрия, тема).
10 — Безопасность: биометрия, secure storage аудит, FLAG_SECURE, обфускация, роли/лимиты backend.
11 — Тесты: pytest + flutter_test + integration_test (логин → поиск → чат → дозы → чек-лист → PDF).
12 — Сборка: `flutter build apk --release --obfuscate`, проверка на эмуляторе, Firebase App Distribution (конфиг + инструкция).
13 — Доки: ARCHITECTURE (диаграмма клиент-сервер), USER_GUIDE (мобильный UI), ADMIN_GUIDE, MOBILE_BUILD_GUIDE.
14 — FINAL_REPORT.md: backend-подъём, сборка APK, LLM_API_KEY, PDF, URL сервера, ограничения.

================================================================
DEFINITION OF DONE
================================================================
[ ] Backend в `docker-compose up`, все endpoints, /docs = реальная схема
[ ] `flutter build apk` без ошибок; APK ставится и работает: логин, 9+ модулей,
    офлайн-кэш, биометрия, голосовой ввод
[ ] Чат: честный отказ + ссылки на источники; офлайн: протокол из кэша без сети
[ ] Все тесты (pytest + flutter test + integration_test) зелёные
[ ] Документация = факту; FINAL_REPORT.md + MOBILE_BUILD_GUIDE.md готовы

СТАРТ: Этап 0, до DoD без остановок. Лог — docs/PROGRESS_LOG.md. Финал — FINAL_REPORT.md.
