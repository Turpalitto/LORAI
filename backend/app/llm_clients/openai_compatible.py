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
        return r.json()["choices"][0]["message"]["content"]
