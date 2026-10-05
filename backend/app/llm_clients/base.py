from abc import ABC, abstractmethod
class BaseLLMClient(ABC):
    @abstractmethod
    def complete(self, system: str, user: str) -> str: ...
