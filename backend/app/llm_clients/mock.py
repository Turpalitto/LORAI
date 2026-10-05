from .base import BaseLLMClient
class MockLLMClient(BaseLLMClient):
    """Детерминированная заглушка: пересказывает контекст без выдумывания."""
    def complete(self, system: str, user: str) -> str:
        return ("[MOCK-ответ на основе контекста]\n" + user[:3000]
                + "\n\nИсточники указаны в блоке context. Дозировки сверяйте с протоколом. Решение принимает врач.")
def get_client() -> BaseLLMClient:
    from ..core.config import settings
    if settings.LLM_PROVIDER == "mock" or not settings.LLM_API_KEY:
        return MockLLMClient()
    from .openai_compatible import OpenAICompatibleClient
    return OpenAICompatibleClient()
