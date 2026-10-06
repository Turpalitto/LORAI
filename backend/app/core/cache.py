"""In-memory TTL-кэш частых запросов + трекер задержек.

Excellence этап 2/6 (скорость на приёме, оптимизация стоимости LLM):
кэширует детерминированные ответы /chat (без session_id) и /search-protocol,
чтобы повторные одинаковые вопросы не пересчитывались. Осознанные ограничения:
- кэш процесс-локальный (сбрасывается при рестарте) — для single-instance MVP
  это приемлемо; для горизонтального масштабирования нужен Redis (см. ROADMAP);
- записи с session_id НЕ кэшируются: раскрытие follow-up зависит от истории
  диалога и кэширование дало бы чужой контекст.
"""
import time
from collections import OrderedDict, deque

class TTLCache:
    def __init__(self, maxsize: int = 256, ttl: float = 300.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._d: OrderedDict[str, tuple[float, object]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        now = time.monotonic()
        try:
            exp, val = self._d.pop(key)
        except KeyError:
            self.misses += 1
            return None
        if exp < now:
            self.misses += 1
            return None
        self._d[key] = (exp, val)  # refresh LRU
        self.hits += 1
        return val

    def set(self, key: str, value: object):
        self._d[key] = (time.monotonic() + self.ttl, value)
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)

    def clear(self):
        """Полная инвалидация: вызывается при загрузке нового документа —
        закэшированные «не найдено» не должны переживать пополнение базы."""
        self._d.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses, "size": len(self._d),
                "hit_rate": round(self.hits / total, 3) if total else 0.0}


cache = TTLCache()
_LAT: deque[float] = deque(maxlen=200)  # последние задержки ответов, мс

def record_latency(ms: float) -> None:
    _LAT.append(ms)

def avg_latency() -> float | None:
    if not _LAT:
        return None
    return round(sum(_LAT) / len(_LAT), 1)
