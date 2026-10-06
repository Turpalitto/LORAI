# KNOWN_ISSUES (обновлено 2026-10-05, аудит-4)
- Docker daemon (Desktop) на машине выключен — `docker compose config` валиден, сборка образов не проверялась.
- Playwright spec лежит (frontend/e2e.smoke.spec.ts), браузеры не ставились — запускать при наличии `npx playwright install`.
- Консоль Windows (cp1251) ломает кириллицу в логах — на данные не влияет.
- sentence-transformers/chromadb не обязательны; без них — TF-IDF с предвычисленным индексом (честный отказ работает).
- pytesseract требует системного tesseract для сканов (tesseract отсутствует → OCR PARTIAL: processing_status=failed + needs_manual_review, тихой потери нет).
- Frontend — 10 страниц (Dashboard/Chat/Search/Dosage/Checklist/DiffDx/Referral/History/Templates/Calculators/Admin), shadcn-стили не внедрены.
- Alembic-миграция 0002_feedback создана в аудите-4 (таблица feedback).
- Flutter SDK не установлен на машине — mobile-фаза (AGENT_BRIEF) заблокирована до установки Flutter 3.x + Android SDK.

- Аудит-5: закрыты — JWT fail-fast, дефолтный doctor-аккаунт (теперь только через env), CORS `*` (allowlist), PII-regex, temp-leak upload, инвалидация кэша при upload, sys.path-магия тестов (pytest.ini).
- doctor-аккаунт: если нужен вход врача на стенде — задайте LORAI_DOCTOR_EMAIL / LORAI_DOCTOR_PASSWORD в .env и перезапустите backend (дефолтного больше нет).
- LORAI_ENV=production + дефолтный JWT_SECRET = старт падает с RuntimeError (осознанный fail-fast, не баг).
- Premium-аудит 2026-10-06 (docs/PREMIUM_AUDIT_REPORT.md): итог 8.4/10, вердикт «готово с оговорками». Открыто: нет SVG-иллюстраций пустых состояний; нет SSE-стриминга ответа чата; нет экспорта логов; upload в админке — через alert и захардкоженный localhost (доработать на VITE_API_URL + тосты); нет прогона на физическом устройстве/скринридере. Flutter-пункты брифа (adaptive icon, splash, APK, haptics) — N/A для web-стека.
- PWA 2026-10-06: установка и офлайн на физическом Android НЕ проверены (нет устройства/эмулятора в сессии; Lighthouse-PWA категории в LH v13+ нет — installability проверена вручную: manifest/SW/icons 200). Явный риск перед пилотом: открыть URL в Chrome на телефоне → «Установить» → standalone → открыть протокол → авиарежим → протокол открывается. Без этого первому врачу не выдавать.
- Backend 2026-10-06: было 56/57 (`test_vector_backend_switch` требовал реальную chromadb); починено моком векторного backend в тесте → 59/59 (включая 2 новых SSE-теста).
