from abc import ABC, abstractmethod
from typing import Iterator
class BaseLLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...
    def stream(self, system: str, user: str) -> Iterator[str]:
        """Живой токен-стрим. Дефолт — один чанк с полным ответом (для
        клиентов без потокового API). SSE-слой сверху не меняется."""
        yield self.complete(system, user)
