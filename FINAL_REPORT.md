# FINAL_REPORT — LORAI (обновлено 2026-10-05, вторая итерация)
База: 22 PDF «ЛОР КЛИНРЕКИ», confidence=high, ICD извлечены.

## Проверено HTTP smoke (сервер :8000, жив):
- /health → True; /protocols?q=H66 → 2; /chat «H66 отит» → refused=False score 0.13 с источниками
- Честный отказ e2e: «перелом лучевой кости» → refused=True
- /auth/login admin+doctor ок; /admin/documents → 22; /history → записи; /dosage → 800 мг
- /diff-diagnosis → 4 нозологии; /favorites add/list ок; /referral-check → True
- pytest backend 10/10 (incl. отказ, роли, magic-байты, дозы, ПДн); vitest 2/2; frontend dist собран
- Upload: лимит 50 МБ + проверка %PDF + 403 для врача (тесты); Alembic baseline 0001_init
- compose config валиден; Docker daemon выключен — сборка образов за пользователем (см. KNOWN_ISSUES)

## Что доделано во 2-й итерации
- Баг пустой БД при старте из backend/ → абсолютные пути ROOT_DIR (config).
- Endpoints: /history, /favorites (POST/GET, JWT), seed_synthetic_data.py, run_local.sh.
- Frontend: 7 разделов (Дашборд, Чат, Протоколы, Дозы, Чек-лист+печать, Шаблоны, Админ) + api-клиент; запуск: `cd frontend; npm install; npm run dev` → :5173.
- @types фиксы, dist собран.

## Пользователю
- Backend уже запущен на :8000 (/docs). Frontend: `npm run dev` в frontend/.
- Real LLM: .env → LLM_PROVIDER=openai + LLM_API_KEY. Порог 0.12 (TF-IDF); с embeddings — 0.75.
- Новые PDF → `python scripts/ingest_pdf.py .`
