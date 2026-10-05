"""Контекстная память диалога в рамках сессии (Excellence-1).

In-memory хранилище последних обменов: короткий follow-up вопрос
(«а для ребёнка 5 лет?») обогащается препаратом/темой из предыдущего
хода. Для production-хранилища заменить _SESSIONS на Redis/БД —
интерфейс (remember/recall/expand) не изменится.
"""
import re
import time
import uuid

_SESSIONS: dict[str, dict] = {}
_TTL_SEC = 30 * 60
_KEEP_LAST = 10

# упоминания препаратов/действующих веществ; [а-я]* покрывает русские
# склонения («амоксициллином», «азитромицина»)
_DRUG_RX = re.compile(
    r"\b(?:амоксициллин|азитромицин|цефуроксим|цефтриаксон|левофлоксацин|"
    r"ксилометазолин|оксиметазолин|мометазон|флутиказон|ибупрофен|парацетамол|"
    r"хлоргексидин|мирамистин|амбробене)[а-я]*|"
    r"\b[a-z]{4,}(?:циллин|мицин|золам|тидин)\b",
    re.I,
)


def _now() -> float:
    return time.time()


def _get(sid: str) -> dict:
    s = _SESSIONS.get(sid)
    if not s or _now() - s["t"] > _TTL_SEC:
        s = {"t": _now(), "turns": []}
        _SESSIONS[sid] = s
    return s


def remember(sid: str, query: str) -> None:
    s = _get(sid)
    s["t"] = _now()
    s["turns"].append(query)
    del s["turns"][: -_KEEP_LAST]


def last_drug(sid: str | None) -> str | None:
    if not sid or sid not in _SESSIONS:
        return None
    for q in reversed(_SESSIONS[sid]["turns"]):
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
