"""Чек-лист приёма из текста клинической рекомендации.

Честный экстрактивный разбор: берём ТОЛЬКО предложения из самого протокола,
ничего не добавляем от себя. Ранее разделы diagnostics.complaints/anamnesis/
physical_exam/lab_tests/instrumental_tests в базе всегда пустые (их никто не
заполняет при ингесте), поэтому чек-лист собирался из «сырых» строк PDF и
выдавал врачу колонтитулы, URL MedElement, даты и маркеры ссылок вида
[13;15;16] в качестве пунктов приёма.
"""
import re

# --- Мусор из PDF: колонтитулы, ссылки, крошки, номера страниц ---
_FURNITURE = [
    re.compile(r"^\s*\d{1,2}\.\d{2}\.\d{4}[,.]?\s*\d{0,2}:?\d{0,2}\s*$"),   # 18.07.2025, 15:05
    re.compile(r"https?://|www\.", re.I),
    re.compile(r"medelement|клинические рекомендации РФ.*>", re.I),
    re.compile(r"^\s*[©(]?\s*(?:ООО|Ассоциац|Минздрав|Национальн)", re.I),
    re.compile(r"^\s*\d{1,3}\s*$"),                                          # номер страницы
    re.compile(r"^\s*(?:с\.|стр\.)\s*\d+", re.I),
    re.compile(r"^\s*[<>|—_=*·•\-\s]+$"),
]
# Маркеры библиографии внутри предложения: [13;15;16], [4, 7]
_CITE = re.compile(r"\[\s*\d+(?:\s*[;,]\s*\d+)*\s*\]")
# Разбиение на предложения: по . ! ? с учётом сокращений
_SENT = re.compile(r"(?<=[.!?])\s+(?=[А-ЯA-ZЁ])")
# Сокращения, после которых точка не заканчивает предложение
_ABBR = re.compile(r"\b(?:см|т\.е|т\.к|т\.д|т\.п|др|рис|табл|напр|мин|мг|мл|кг|г|мм|см|ст|стр)\.$", re.I)
# Обрывок с середины предложения (разрез текста по заголовку) — начинается со строчной
_LOWER_START = re.compile(r"^[а-яё]")
# Колонтитул/крошка внутри строки
_INLINE_JUNK = re.compile(r">\s*Клинические рекомендации|MedElement|https?://|www\.|©\s*\d{4}", re.I)
# Методическая шапка рекомендации, приклеенная к клиническому предложению
_METHOD = re.compile(r"^\s*(?:Уровень убедительности рекомендаций[^)]*\)|Уровень достоверности доказательств[^)]*\)|"
                     r"Комментарии\s*:)\s*", re.I)
# Методический хвост внутри предложения: «... Уровень убедительности рекомендаций C (...)»
_METHOD_TAIL = re.compile(r"\s*(?:Уровень убедительности рекомендаций|Уровень достоверности доказательств|"
                          r"Комментарии\b|Источник\b).*$", re.I | re.S)
# Заголовок раздела, приклеенный к первому предложению при вырезании по заголовкам
_HEADING_PREFIX = re.compile(
    r"^\s*(?:Лабораторные диагностические исследования|Иные диагностические исследования|"
    r"Инструментальные диагностические исследования|Дополнительная информация[^)]*\)|"
    r"Критерии установления диагноза\s*[.:]?|Физикальное обследование|Жалобы|"
    r"Анамнез(?:\s+(?:жизни|заболевания))?\s*[.:]?|Диагностика\s*[.:]?|Обследование\s*[.:]?)\s*",
    re.I)
# Хвост-обрывок от разреза текста по заголовку: «... воздействием или состояний)
# медицинские показания и противопоказания к Критерии установления диагноза».
_TAIL_CUT = re.compile(
    r"\s+(?:или состояний\)|медицинские показания и противопоказания|"
    r"Критерии установления диагноза|Клинические рекомендации РФ).*$", re.I | re.S)
# Мусорные вкрапления вёрстки: номера страниц вида 3/32, «изол», одиночные знаки
_PAGE_FRAGMENT = re.compile(r"\b\d{1,3}/\d{1,3}\b")

# Минимальная длина осмысленного пункта: короче — это обрывки вёрстки.
_MIN_LEN = 45
_MAX_PER_BLOCK = 8
_MAX_TOTAL = 24

# Классификация предложений по разделам приёма (порядок важен).
_BLOCK_RULES: list[tuple[str, re.Pattern]] = [
    ("Жалобы", re.compile(r"\bжалоб|беспоко\w+|предъявля\w+", re.I)),
    ("Анамнез", re.compile(r"\bанамнез|давност|со слов|развива\w+|предшеств\w+|заболел|в течение \d|длительн\w+ течен", re.I)),
    ("Осмотр", re.compile(r"\bосмотр|пальпац|отоскоп|риноскоп|фарингоскоп|ларингоскоп|эпифарингоскоп|"
                          r"миндалин|лимфоузл|лимфатическ|гиперем|налёт|налет|инфильтрац|"
                          r"тризм|отёк|отек|асимметр|зондирован|перкусс|аускультац", re.I)),
    ("Лабораторно", re.compile(r"\bанализ|лаборатор|\bкров|лейкоцит|СОЭ|С-реактивн|прокальцитонин|"
                               r"посев|ПЦР|иммуноглобулин|биохим|антиген|серолог|цитолог|гистолог", re.I)),
    ("Инструментально", re.compile(r"\bКТ\b|\bМРТ\b|\bУЗИ\b|рентген|аудиометр|тимпанометр|эндоскоп|"
                                   r"отомикроскоп|микроскоп|камертон|биопси|пункц|томограф", re.I)),
]


def _is_furniture(line: str) -> bool:
    return any(rx.search(line) for rx in _FURNITURE)


def _clean_sentence(s: str) -> str:
    """Снять методическую шапку/хвост и заголовки, не меняя смысл фразы."""
    s = _METHOD.sub("", s)
    s = _HEADING_PREFIX.sub("", s)
    s = _METHOD_TAIL.sub("", s)
    s = _TAIL_CUT.sub("", s)
    s = _PAGE_FRAGMENT.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .,-–—:;")
    return s


# Пункт чек-листа должен читаться с одного взгляда: длинные перечисления режем
# по точкам с запятой и нумерованным элементам — без переписывания текста.
_SPLIT_POINT = re.compile(r";\s+|\s(?=\d{1,2}[.)]\s)")
_MAX_POINT = 260


def _split_long(s: str) -> list[str]:
    if len(s) <= _MAX_POINT:
        return [s]
    parts = [p.strip(" .,;:-–—") for p in _SPLIT_POINT.split(s)]
    # Хвосты перечисления, начинающиеся со строчной («...узлов, а специалистами»),
    # не самостоятельные пункты — оставляем ведущую часть предложения.
    parts = [p for p in parts if len(p) >= _MIN_LEN and not _LOWER_START.match(p)]
    if not parts:
        return [s[:_MAX_POINT].rsplit(" ", 1)[0] + "…"]
    out: list[str] = []
    for p in parts:
        if len(p) > _MAX_POINT:
            out.append(p[:_MAX_POINT].rsplit(" ", 1)[0] + "…")
        else:
            out.append(p)
    return out


def _sentences(raw: str) -> list[str]:
    """Склеить переносы вёрстки в предложения и выбросить мусор PDF."""
    kept = [ln.strip() for ln in (raw or "").replace("\r", "\n").split("\n") if ln.strip()]
    kept = [ln for ln in kept if not _is_furniture(ln)]
    if not kept:
        return []
    text = " ".join(kept)
    text = _CITE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    out: list[str] = []
    for chunk in _SENT.split(text):
        s = chunk.strip(" \t-–—•")
        if not s:
            continue
        # Точка после «см./мг/стр.» — не конец предложения: приклеиваем обратно.
        if out and _ABBR.search(out[-1]):
            out[-1] = (out[-1] + " " + s).strip()
            continue
        out.append(s)

    cleaned: list[str] = []
    for s in out:
        if _INLINE_JUNK.search(s):
            continue
        s = _clean_sentence(s)
        # Обрывок с середины предложения отсекаем уже после снятия шапки:
        # «Уровень убедительности рекомендаций C (...) идут данные...» → строчная.
        if not s or _LOWER_START.match(s):
            continue
        if len(s) >= _MIN_LEN:
            cleaned.extend(_split_long(s))
    return cleaned


def build_checklist(protocol: dict) -> dict:
    """Вернуть чек-лист: блоки приёма + пункты строго из текста протокола.

    Структурированные разделы используются, если они заполнены; иначе
    предложения из diagnostics.raw раскладываются по блокам по ключевым
    словам. Ничего не додумываем: если текста нет — чек-лист пуст и
    needs_source=True, чтобы интерфейс честно отправил врача к оригиналу.
    """
    d = (protocol.get("sections") or {}).get("diagnostics", {}) or {}
    blocks: list[dict] = []

    structured = [
        ("complaints", "Жалобы"), ("anamnesis", "Анамнез"), ("physical_exam", "Осмотр"),
        ("lab_tests", "Лабораторно"), ("instrumental_tests", "Инструментально"),
    ]
    for key, label in structured:
        v = d.get(key) or []
        pts = [str(x).strip() for x in v if str(x).strip()]
        if pts:
            blocks.append({"block": label, "points": pts[:_MAX_PER_BLOCK]})

    auto = False
    if not blocks:
        # В базе структурированных подразделов нет — собираем из сырого текста.
        buckets: dict[str, list[str]] = {label: [] for label, _rx in _BLOCK_RULES}
        other: list[str] = []
        seen: set[str] = set()

        for s in _sentences(d.get("raw", "")):
            norm = re.sub(r"\W+", " ", s.lower()).strip()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            for label, rx in _BLOCK_RULES:
                if rx.search(s):
                    buckets[label].append(s)
                    break
            else:
                other.append(s)

        for label, _rx in _BLOCK_RULES:
            pts = buckets.get(label) or []
            if pts:
                blocks.append({"block": label, "points": pts[:_MAX_PER_BLOCK]})

        # Неразобранные клинические предложения — отдельным блоком, а не свалкой строк.
        rest = other[:_MAX_PER_BLOCK]
        if rest:
            blocks.append({"block": "Из протокола", "points": rest})
        auto = bool(blocks)

    # Общий предел, чтобы чек-лист оставался рабочим документом приёма.
    total = 0
    trimmed: list[dict] = []
    for b in blocks:
        room = _MAX_TOTAL - total
        if room <= 0:
            break
        pts = b["points"][:room]
        if pts:
            trimmed.append({**b, "points": pts})
            total += len(pts)

    return {
        "nosology": protocol.get("nosology"),
        "title": protocol.get("title"),
        "checklist": trimmed,
        "auto_generated": auto,
        "needs_source": not trimmed,
        "source_note": (
            "Пункты собраны автоматически из текста клинической рекомендации "
            "и не заменяют оригинал — сверьте формулировки с полным текстом КР."
        ) if auto else "",
    }
