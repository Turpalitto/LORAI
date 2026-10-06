import httpx
from .base import BaseLLMClient
from ..core.config import settings
class OpenAICompatibleClient(BaseLLMClient):
    """Работает с OpenAI / OpenRouter / Together / локальным vLLM (OpenAI-совместимые)."""
    def complete(self, system: str, user: str) -> str:
        r = httpx.post(f"{settings.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json={"model": settings.LLM_MODEL,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                  "temperature": 0}, timeout=60)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"].get("content") or ""
        if not text.strip():
            raise RuntimeError("Провайдер вернул пустой ответ (модель не сгенерировала контент)")
        return text
    def stream(self, system: str, user: str):
        """Настоящий токен-стрим (OpenAI-совместимый SSE). Каждая yield —
        дельта контента одного чанка; [DONE] и пустые дельты пропускаются."""
        import json as _json
        with httpx.stream("POST", f"{settings.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
                json={"model": settings.LLM_MODEL,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                      "temperature": 0, "stream": True}, timeout=120) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = _json.loads(payload)["choices"][0]["delta"]
                except Exception:
                    continue
                text = delta.get("content")
                if text:
                    yield text
