# KNOWN_ISSUES
- Docker daemon (Desktop) на машине выключен — `docker compose config` валиден, сборка образов не проверялась.
- Playwright spec лежит (frontend/e2e.smoke.spec.ts), браузеры не ставились — запускать при наличии `npx playwright install`.
- Консоль Windows (cp1251) ломает кириллицу в логах — на данные не влияет.
- sentence-transformers/chromadb не обязательны; без них — TF-IDF (точность ниже, но честный отказ работает).
- pytesseract требует системного tesseract для сканов.
- Frontend — MVP (чат+поиск); shadcn-стили и остальные 7 страниц — следующий шаг.
