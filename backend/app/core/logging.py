"""Логи с request-id.

Раньше лог был 9 строк: сообщения в stdout без корреляции, и при разборе
инцидента нельзя было связать строку «разбор не удался» с конкретным
запросом. Теперь каждый HTTP-запрос получает id (из `X-Request-ID` или
сгенерированный), он попадает в заголовок ответа и в каждую строку лога,
включая фоновые задачи, запущенные внутри запроса.
"""
import contextvars
import logging
import sys
import uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


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


def get_logger(name: str = "lorai"):
    l = logging.getLogger(name)
    if not l.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(_RequestIdFormatter(
            "%(asctime)s [%(levelname)s] [req=%(request_id)s] %(name)s: %(message)s"))
        l.addHandler(h)
        l.setLevel(logging.INFO)
        l.propagate = False
    return l


log = get_logger()
