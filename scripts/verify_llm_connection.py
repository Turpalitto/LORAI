"""Сухой прогон подключения к LLM (go-live): ключ валиден, ответ приходит,
формат совместим с SSE-парсером /chat/stream. Ключ в вывод НЕ печатается.

Запуск:  python scripts/verify_llm_connection.py [--base-url ... --model ...]
Коды выхода: 0 — всё ок; 1 — mock/нет ключа (не ошибка, а «ещё не включено»);
2 — ключ/провайдер отвечает с ошибкой (смотреть текст, чинить .env).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def _load_dotenv(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))
    except FileNotFoundError:
        pass


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="Ответь одним словом: тест.",
                    help="Тестовый промпт (короткий, дешёвый)")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--model", default="")
    a = ap.parse_args()

    _load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    provider = os.getenv("LLM_PROVIDER", "mock")
    base = a.base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = a.model or os.getenv("LLM_MODEL", "gpt-4o-mini")
    key = os.getenv("LLM_API_KEY", "")

    print(f"[1/4] provider={provider} base={base} model={model}")
    if provider == "mock" or not key:
        print("[!] LLM не включён (mock или пустой LLM_API_KEY). "
              "Это нормально до go-live: впишите ключ в .env и перезапустите.")
        return 1
    print(f"[2/4] ключ задан (длина {len(key)}, префикс {key[:4]}****)")

    import httpx
    try:
        r = httpx.post(f"{base}/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model,
                             "messages": [{"role": "user", "content": a.prompt}],
                             "temperature": 0, "max_tokens": 32},
                       timeout=60)
    except Exception as e:
        print(f"[X] сеть недоступна: {type(e).__name__}: {e}")
        return 2
    if r.status_code == 401:
        print("[X] 401: ключ отклонён провайдером. Проверьте LLM_API_KEY и provider/base_url.")
        return 2
    if r.status_code == 404:
        print(f"[X] 404: модель '{model}' не найдена у провайдера. Сверьте LLM_MODEL.")
        return 2
    try:
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
    except Exception as e:
        print(f"[X] неожиданный формат ответа ({r.status_code}): {str(e)[:200]}")
        print("    body:", r.text[:300])
        return 2
    if not text.strip():
        print("[X] провайдер вернул пустой контент (такое бывает у reasoning/free-моделей). "
              "Для пилота нужна стабильная платная модель.")
        return 2
    print(f"[3/4] ответ получен ({len(text)} символов): {text[:80]!r}")

    try:
        deltas = 0
        with httpx.stream("POST", f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model,
                                "messages": [{"role": "user", "content": a.prompt}],
                                "temperature": 0, "max_tokens": 32, "stream": True},
                          timeout=120) as s:
            s.raise_for_status()
            for line in s.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                if json.loads(payload)["choices"][0]["delta"].get("content"):
                    deltas += 1
    except Exception as e:
        print(f"[X] стрим-режим недоступен: {type(e).__name__}: {str(e)[:200]}")
        print("    /chat/stream будет работать в режиме нарезки (фолбэк), но живой стрим — нет.")
        return 2
    if deltas == 0:
        print("[X] стрим открылся, но дельт нет — парсер SSE /chat/stream голодать не будет, "
              "но проверьте провайдера.")
        return 2
    print(f"[4/4] SSE-стрим ок: {deltas} дельт, формат совместим с /chat/stream.")
    print("OK: можно включать (LLM_PROVIDER уже не mock), перезапустите backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
