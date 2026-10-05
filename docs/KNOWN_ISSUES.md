# KNOWN_ISSUES (обновлено 2026-10-05, аудит-4)
- Docker daemon (Desktop) на машине выключен — `docker compose config` валиден, сборка образов не проверялась.
- Playwright spec лежит (frontend/e2e.smoke.spec.ts), браузеры не ставились — запускать при наличии `npx playwright install`.
- Консоль Windows (cp1251) ломает кириллицу в логах — на данные не влияет.
- sentence-transformers/chromadb не обязательны; без них — TF-IDF с предвычисленным индексом (честный отказ работает).
- pytesseract требует системного tesseract для сканов (tesseract отсутствует → OCR PARTIAL: processing_status=failed + needs_manual_review, тихой потери нет).
- Frontend — 10 страниц (Dashboard/Chat/Search/Dosage/Checklist/DiffDx/Referral/History/Templates/Calculators/Admin), shadcn-стили не внедрены.
- Alembic-миграция 0002_feedback создана в аудите-4 (таблица feedback).
- Flutter SDK не установлен на машине — mobile-фаза (AGENT_BRIEF) заблокирована до установки Flutter 3.x + Android SDK.
