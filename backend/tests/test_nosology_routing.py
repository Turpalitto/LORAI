"""Маршрутизация по нозологии: распознавание протокола из текста вопроса.

Зачем: косинусы e5 на клинических вопросах сжаты в 0.80–0.87, поэтому «лечение
острого среднего отита» и «лечение острого синусита» отличаются на 0.005–0.01 и
ранжируются почти случайно. Раздел протокола маршрутизируется (section_hint), а
нозология — нет; на hold-out это стоило 4 вопросов из 22, где правильный
протокол стоял на 6–13 месте (docs/RETRIEVAL_EVAL.md §11).

Тесты здесь быстрые: детектор — чистые регулярки, стор поднимается на TF-IDF,
модель эмбеддингов не нужна.
"""
import pytest

from app.knowledge_base.vector_store import VectorStore, _norm_nos
from app.rag.retriever import nosology_hint, retrieve


# ---------- распознавание нозологии ----------
@pytest.mark.parametrize("q,expected", [
    ("чем лечить острый гнойный средний отит у взрослого", "Отит средний острый"),
    ("хронический отит: дырка в перепонке и запах из уха", "Хронический средний отит"),
    ("какие капли капать в ухо при наружном отите", "Наружные отиты"),
    ("после антибиотиков в ухе плесень и зуд", "Грибковый отит"),
    ("частые ангины: когда убирать миндалины", "Хронический тонзиллит"),
    ("боль в горле и налёт на миндалинах", "Острый тонзиллит и фарингит"),
    ("аденоиды 3 степени — удалять или лечить", "Гипертрофия аденоидов"),
    ("носовые полипы и не чувствую запахи", "Полипозный риносинусит"),
    ("искривлена перегородка, не дышу одной ноздрёй", "Деформация перегородки носа"),
    ("после концерта заложило уши и звенит второй день", "Потеря слуха, вызванная шумом"),
    ("нужна ли операция при отосклерозе", "Отосклероз"),
    ("кружится голова приступами, болезнь Меньера", "Болезнь Меньера"),
    ("круглогодично заложен нос и зудит, чихаю", "Аллергический ринит"),
    ("ударился носом, кровь не останавливается", "Травма носа"),
    ("после удара по уху кровь из прохода", "Травма уха"),
    # 1.11.0: вопросы без названия болезни. Добавлены только те симптомы, что
    # на замере давали промах (docs/RETRIEVAL_EVAL.md §12): козелок, тризм,
    # «охрип». Остальные симптомокомплексы уже стояли первыми без правил.
    ("болит ухо при нажатии на козелок", "Наружные отиты"),
    ("боль при оттягивании ушной раковины", "Наружные отиты"),
    ("после ангины трудно открывать рот", "Паратонзиллярный абсцесс"),
    ("неделю лечил горло, больно широко открывать рот", "Паратонзиллярный абсцесс"),
    ("после крика охрип и говорит шёпотом", "Острый ларингит"),
])
def test_nosology_is_recognized(q, expected):
    assert nosology_hint(q) == expected


def test_specific_form_beats_generic():
    """«хронический отит» не должен уходить в общий «отит» (острый средний)."""
    assert nosology_hint("хронический средний отит: перфорация") == "Хронический средний отит"


def test_trauma_beats_symptom():
    """«осиплость после удара в шею» — травма гортани, а не ларингит.

    Симптом «осиплость» стоит в правилах ларингита ниже: если порядок правил
    нарушить, вопрос о травме получит терапевтический протокол.
    """
    assert nosology_hint("осиплость после удара в шею") == "Травма гортани"
    assert nosology_hint("травма гортани: осиплость и боль в шее") == "Травма гортани"


def test_trismus_after_trauma_is_not_abscess():
    """«трудно открывать рот» — симптом и абсцесса, и травмы гортани.

    Правило тризма стоит после травм намеренно: иначе «трудно открывать рот
    после удара в шею» уходило бы в паратонзиллярный абсцесс.
    """
    assert nosology_hint("трудно открывать рот после удара в шею") == "Травма гортани"
    assert nosology_hint("после ангины трудно открывать рот") == "Паратонзиллярный абсцесс"


@pytest.mark.parametrize("q", [
    "расскажи про ухо",
    "боль в ухе и температура у грудничка",
    "после антибиотиков в ухе появился налёт и зуд",  # клиническое описание без термина
    "кружится голова приступами, ухо заложило и шумит",
    "насморк больше недели, болит голова и щека",  # синусит по симптомам, без термина
    # 1.11.0: правила симптомов не должны превращаться в «угадайку».
    "храпит мужчина 45 лет",  # храп у взрослого — не аденоиды
    "боль в горле при глотании",  # без налёта/температуры — тонзиллит не утверждаем
    "",
])
def test_abstains_when_unsure(q):
    """Молчание — часть контракта: неверная нозология хуже отсутствия.

    Буст чужого протокола поднимает его выше правильного, поэтому при
    неоднозначности детектор обязан вернуть None.
    """
    assert nosology_hint(q) is None


def test_nosology_names_have_no_trailing_spaces():
    """Регресс: названия из PDF приходили с хвостовым пробелом, из-за чего
    фильтр по нозологии молча не находил ни одного чанка."""
    assert _norm_nos("Отит средний острый ") == _norm_nos("отит средний острый")


# ---------- влияние буста на ранжирование ----------
TXT = "лечение отита антибиотик"


def _store(tmp_path, monkeypatch, docs) -> VectorStore:
    monkeypatch.setenv("VECTOR_BACKEND", "tfidf")
    vs = VectorStore(str(tmp_path))
    for nosology, section in docs:
        vs.add([{"text": TXT, "section": section}],
               {"title": "КР", "nosology": nosology, "document": "КР", "icd10_codes": []})
    return vs


def test_boost_lifts_named_nosology(tmp_path, monkeypatch):
    """Текст чанков одинаковый — порядок задаёт только буст."""
    vs = _store(tmp_path, monkeypatch, [("Острый синусит", "treatment"),
                                        ("Отит средний острый", "treatment")])
    monkeypatch.setenv("NOSOLOGY_BOOST", "1.0")
    plain = vs.search(TXT, k=2)
    monkeypatch.setenv("NOSOLOGY_BOOST", "1.5")
    boosted = vs.search(TXT, k=2, nosology_boost="Отит средний острый")

    assert plain[0]["nosology"] == "Острый синусит", "без буста порядок исходный"
    assert plain[0]["score"] == plain[1]["score"], "скоры равны — иначе тест не про буст"
    assert boosted[0]["nosology"] == "Отит средний острый"


def test_boost_matches_name_with_trailing_space(tmp_path, monkeypatch):
    """Старые индексы хранят название с хвостовым пробелом — буст обязан сработать."""
    vs = _store(tmp_path, monkeypatch, [("Острый синусит", "treatment"),
                                        ("Отит средний острый ", "treatment")])
    monkeypatch.setenv("NOSOLOGY_BOOST", "1.5")
    out = vs.search(TXT, k=2, nosology_boost="Отит средний острый")
    assert out[0]["nosology"].strip() == "Отит средний острый"


def test_score_stays_honest_when_nosology_boosted(tmp_path, monkeypatch):
    """Буст меняет порядок, но не подменяет score: иначе гейт отказа врал бы."""
    vs = _store(tmp_path, monkeypatch, [("Острый синусит", "treatment"),
                                        ("Отит средний острый", "treatment")])
    monkeypatch.setenv("NOSOLOGY_BOOST", "1.0")
    raw = {c["nosology"]: c["score"] for c in vs.search(TXT, k=2)}
    monkeypatch.setenv("NOSOLOGY_BOOST", "5.0")
    boosted = {c["nosology"]: c["score"] for c in vs.search(TXT, k=2, nosology_boost="Отит средний острый")}
    assert raw == boosted


def test_appendix_chunks_are_not_boosted(tmp_path, monkeypatch):
    """Приложения КР административные: буст не должен вытаскивать их в топ.

    Живой случай: «после концерта заложило уши» — первым вставал чанк
    приложения о медико-социальной экспертизе, потому что он из того же
    протокола. Раздел `appendix` из-под буста выведен.
    """
    vs = _store(tmp_path, monkeypatch, [("Острый синусит", "treatment"),
                                        ("Отит средний острый", "appendix")])
    monkeypatch.setenv("NOSOLOGY_BOOST", "5.0")
    out = vs.search(TXT, k=2, nosology_boost="Отит средний острый")
    assert out[0]["nosology"] == "Острый синусит", "приложение получило буст нозологии"


def test_client_filter_matches_despite_trailing_space(tmp_path, monkeypatch):
    """Явный фильтр по нозологии работал только для 1 протокола из 22."""
    vs = _store(tmp_path, monkeypatch, [("Острый синусит", "treatment"),
                                        ("Отит средний острый ", "treatment")])
    out = vs.search(TXT, k=5, filters={"nosology": "Отит средний острый"})
    assert [c["nosology"].strip() for c in out] == ["Отит средний острый"]


# ---------- связка retrieve ----------
class _StubStore:
    def __init__(self):
        self.nos = "не вызван"

    def search(self, query, k=6, filters=None, section_boost=None, general_cap=None,
               nosology_boost=None):
        self.nos = nosology_boost
        return [{"text": "x", "score": 0.5, "section": "treatment", "nosology": "Отит средний острый"}]


def test_retrieve_passes_nosology_hint():
    store = _StubStore()
    retrieve(store, "чем лечить острый гнойный средний отит")
    assert store.nos == "Отит средний острый"


def test_explicit_filter_wins_over_hint():
    """Врач выбрал протокол руками — догадку не подмешиваем."""
    store = _StubStore()
    retrieve(store, "чем лечить острый гнойный средний отит",
             filters={"nosology": "Острый синусит"})
    assert store.nos is None


def test_generic_question_gets_no_hint():
    store = _StubStore()
    retrieve(store, "расскажи про ухо")
    assert store.nos is None
