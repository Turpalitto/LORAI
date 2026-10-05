# mobile/ — Flutter-клиент LORAI (каркас)

Статус: **BLOCKED** — Flutter SDK не установлен в окружении (см. DECISIONS #15).

## Что внутри

- `pubspec.yaml` — зависимости: `http` (API), `shared_preferences` (токен)
- `lib/main.dart` — экран чата: POST /chat, хранение токена, дисклеймер
- Дальше по EXCELLENCE_BRIEF 2/2.5: поиск протоколов, калькуляторы
  (Centor/PTA), избранное, виджеты, OCR назначений, haptics, офлайн-пакет

## Как поднять (когда будет SDK)

```bash
# 1. Flutter 3.x: https://docs.flutter.dev/get-started/install/macos
flutter --version            # >= 3.0.0
# 2. Зависимости и запуск (backend на :8000)
cd mobile && flutter pub get
# эмулятор Android: base = http://10.0.2.2:8000 (уже в коде)
# iOS-симулятор: base = http://127.0.0.1:8000
flutter run
flutter test
```

## API-контракт (совпадает с web)

- `POST /login {email,password} → {token}`
- `POST /chat {message, session_id?} → {answer, sources, ...}`
- см. `docs/USER_GUIDE.md`, `frontend/src/`
