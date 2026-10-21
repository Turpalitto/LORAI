"""Логи с request-id и необязательным JSON-форматом.

Раньше лог был 9 строк: сообщения в stdout без корреляции, и при разборе
инцидента нельзя было связать строку «разбор не удался» с конкретным
запросом. Теперь каждый HTTP-запрос получает id (из `X-Request-ID` или
сгенерированный), он попадает в заголовок ответа и в каждую строку лога,
включая фоновые задачи, запущенные внутри запроса.

`LOG_FORMAT=json` переключает вывод на одну JSON-строку на запись — это то,
что читают Loki/ELK/CloudWatch. По умолчанию остаётся текстовый формат:
человеку в терминале он понятнее, а машине хватает и его (request-id есть
в обеих формах).
"""
import contextvars
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

from .config import settings

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Атрибуты, которые есть у любой записи logging. Всё, что пришло через extra=,
# добавляем в JSON отдельными полями (иначе теряется контекст: user, doc_id…).
_STD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message", "asctime", "request_id", "taskName"}


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize_request_id(value: str | None) -> str:
    """Клиентский id принимаем только как короткий [A-Za-z0-9_.-], иначе свой.

    Заголовок приходит снаружи: без фильтра в лог и в ответ можно протащить
    произвольную строку (в т.ч. перевод строки — подделка записей журнала).
    """
    v = (value or "").strip()
    if v and len(v) <= 64 and all(c.isalnum() or c in "-_." for c in v):
        return v
    return new_request_id()


def set_request_id(rid: str) -> contextvars.Token:
    return _request_id.set(rid)


def reset_request_id(token: contextvars.Token) -> None:
    try:
        _request_id.reset(token)
    except ValueError:
        pass


def get_request_id() -> str:
    return _request_id.get()


class _RequestIdFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return super().format(record)


class _JsonFormatter(logging.Formatter):
    """Одна строка JSON на запись. Ключи стабильные: коллектор не должен
    зависеть от формата сообщения."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
                          .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", None) or get_request_id(),
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STD_ATTRS or key.startswith("_"):
                continue
            payload.setdefault(key, value)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _json_format() -> bool:
    # settings читает LOG_FORMAT из окружения; прямое os.getenv — запасной путь
    # для случая, когда лог поднимают до инициализации настроек.
    fmt = (getattr(settings, "LOG_FORMAT", "") or os.getenv("LOG_FORMAT") or "text")
    return str(fmt).strip().lower() in {"json", "jsonl", "structured"}


def get_logger(name: str = "lorai"):
    l = logging.getLogger(name)
    if not l.handlers:
        h = logging.StreamHandler(sys.stdout)
        if _json_format():
            h.setFormatter(_JsonFormatter())
        else:
            h.setFormatter(_RequestIdFormatter(
                "%(asctime)s [%(levelname)s] [req=%(request_id)s] %(name)s: %(message)s"))
        l.addHandler(h)
        l.setLevel(logging.INFO)
        l.propagate = False
    return l


log = get_logger()
