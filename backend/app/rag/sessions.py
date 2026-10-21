"""Контекстная память диалога в рамках сессии (Excellence-1).

In-memory хранилище последних обменов: короткий follow-up вопрос
(«а для ребёнка 5 лет?») обогащается препаратом/темой из предыдущего
хода. Для production-хранилища заменить _SESSIONS на Redis/БД —
интерфейс (remember/recall/expand) не изменится.
"""
import re
import threading
import time
import uuid

_SESSIONS: dict[str, dict] = {}
_SESSIONS_LOCK = threading.RLock()
_TTL_SEC = 30 * 60
_KEEP_LAST = 10

# упоминания препаратов/действующих веществ; [а-я]* покрывает русские
# склонения («амоксициллином», «азитромицина»)
# Вторая ветка — латиница: раньше там стояли КИРИЛЛИЧЕСКИЕ суффиксы после
# `[a-z]{4,}` («amoxicillin» + «циллин»), поэтому ветка не срабатывала никогда
# и латинские названия препаратов в follow-up не подхватывались.
_DRUG_RX = re.compile(
    r"\b(?:амоксициллин|азитромицин|цефуроксим|цефтриаксон|левофлоксацин|"
    r"ксилометазолин|оксиметазолин|мометазон|флутиказон|ибупрофен|парацетамол|"
    r"хлоргексидин|мирамистин|амбробене)[а-я]*|"
    r"\b[a-z]{4,}(?:cillin|mycin|zolam|tidine)\b",
    re.I,
)


def _now() -> float:
    return time.time()


# Порог, после которого подчищаем просроченные сессии. Раньше они удалялись
# только при повторном обращении к тому же sid: за сутки работы в словаре
# накапливались тысячи мёртвых записей.
_PRUNE_AT = 500


def _prune(now: float | None = None) -> int:
    now = _now() if now is None else now
    with _SESSIONS_LOCK:
        dead = [k for k, v in list(_SESSIONS.items()) if now - v["t"] > _TTL_SEC]
        for k in dead:
            _SESSIONS.pop(k, None)
    return len(dead)


def _get(sid: str) -> dict:
    """Сессия под замком: `remember`/`_prune` дергаются из пула потоков
    FastAPI, а незащищённый dict при одновременной вставке и очистке даёт
    RuntimeError «dictionary changed size during iteration»."""
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(sid)
        if not s or _now() - s["t"] > _TTL_SEC:
            s = {"t": _now(), "turns": []}
            _SESSIONS[sid] = s
            if len(_SESSIONS) > _PRUNE_AT:
                _prune()
        return s


def remember(sid: str, query: str) -> None:
    with _SESSIONS_LOCK:
        s = _get(sid)
        s["t"] = _now()
        s["turns"].append(query)
        del s["turns"][: -_KEEP_LAST]


def last_drug(sid: str | None) -> str | None:
    if not sid:
        return None
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(sid)
        if not s:
            return None
        turns = list(s["turns"])
    for q in reversed(turns):
        m = _DRUG_RX.search(q or "")
        if m:
            return m.group(0)
    return None


def expand_query(query: str, sid: str | None) -> str:
    """Короткий follow-up + известный препарат → расширенный запрос для ретривера."""
    if sid and len((query or "").split()) <= 8:
        drug = last_drug(sid)
        if drug and drug.lower() not in (query or "").lower():
            return f"{query} {drug}"
    return query


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
