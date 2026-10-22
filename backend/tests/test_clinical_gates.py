"""Клинические гейты: маршрутизация раздела, домен-гейт, проверка чисел, промпт.

Закрывают находки аудита 2026-10-21: «рекоменд/помощ/ведени» в лечении
перехватывали диагностику, «рецидив» уводил лечение в профилактику,
дозировочная лексика и «ух/уш/нос» пропускали вне-доменные вопросы, а
проверка чисел ругалась на номер страницы в цитате.
"""
import pytest


# ------------------------------------------------------------ H1: маршрутизация
@pytest.mark.parametrize("q,want", [
    ("какие рекомендации по диагностике острого отита", "diagnostics"),
    ("лечение рецидивирующего ларингита", "treatment"),
    ("чем лечить рецидив ангины", "treatment"),
    ("профилактика рецидивов отита", "prevention"),
    ("какие симптомы при рецидиве", "diagnostics"),
    ("неотложная помощь при стенозе гортани", "treatment"),
    ("стоит ли госпитализировать и как лечить абсцесс", "referral_criteria"),
    ("что такое болезнь Меньера", "definition"),
    # 1.11.0: жалоба без названия болезни («заложен нос», «тяжесть в лице»)
    # не маршрутизировалась вообще — в топ-6 шло определение.
    ("заложен нос и тяжесть в области лица", "diagnostics"),
])
def test_section_hint_not_stolen_by_generic_words(q, want):
    from app.rag.retriever import section_hint

    assert section_hint(q) == [want]


# ------------------------------------------------------------- H3: домен-гейт
@pytest.mark.parametrize("q", [
    "доза инсулина ребёнку",
    "ушиб колена что делать",
    "ухудшение после инфаркта",
    "носит ли маску при гриппе",
    "какой антибиотик при пневмонии",
    # Стражи для маркеров, добавленных в 1.11.0: «ше» (шея) и «горл».
    "шелушение кожи на лице",
    "болит поясница при наклоне вперёд",
    "сыпь на коже и сильный зуд",
])
def test_out_of_domain_questions_have_no_lor_signal(q):
    from app.rag.anti_hallucination import has_lor_signal

    assert has_lor_signal(q) is False, q


@pytest.mark.parametrize("q", [
    "болит ухо справа",
    "заложило уши после концерта",
    "нос не дышит, нужен спрей",
    "чем лечить отит у ребёнка",
    "доза амоксициллина ребёнку",
    "шкала SNOT-22 при полипозном риносинусите",
    # 1.11.0: вопросы без названия болезни отсекались домен-гейтом —
    # «ушная раковин» стоял в именительном падеже, «горло» не было вовсе.
    "болит ухо при нажатии на козелок",
    "боль при оттягивании ушной раковины и зуд в проходе",
    "неделю лечил горло, стало больно широко открывать рот",
    "трудно открывать рот после удара в шею",
])
def test_lor_questions_still_have_signal(q):
    from app.rag.anti_hallucination import has_lor_signal

    assert has_lor_signal(q) is True, q


# ----------------------------------------------------------- H4: числа в ответе
CTX = [{"text": "Амоксициллин 500 мг 3 раза в сутки 7 дней. Раствор 5 мл."}]


def test_page_number_in_citation_is_not_flagged():
    """«Стр. 12» — адрес цитаты, а не факт из протокола."""
    from app.rag.anti_hallucination import check_numbers

    ans = "Амоксициллин 500 мг 3 раза в сутки. [Документ: КР, Раздел: Лечение, Стр. 12]"
    assert "⚠️" not in check_numbers(ans, CTX)


def test_unknown_number_is_still_flagged():
    from app.rag.anti_hallucination import check_numbers

    ans = "Амоксициллин 750 мг 3 раза в сутки."
    assert "⚠️" in check_numbers(ans, CTX) and "750" in check_numbers(ans, CTX)


def test_unit_substitution_is_flagged():
    """Число есть, единица другая: «5 мг» при «5 мл» в источнике."""
    from app.rag.anti_hallucination import check_numbers

    out = check_numbers("Дай 5 мг препарата.", CTX)
    assert "⚠️" in out


def test_thousands_separator_still_matches():
    from app.rag.anti_hallucination import check_numbers

    ctx = [{"text": "Разовая доза 1000 мг."}]
    assert "⚠️" not in check_numbers("Доза 1 000 мг.", ctx)


# ----------------------------------------------------------------- H2: промпт
def test_prompt_forbids_transfer_between_nosologies():
    from app.rag.prompt_builder import build_prompt

    chunks = [{"document": "Острый синусит", "section": "treatment", "text": "Амоксициллин 500 мг"},
              {"document": "Отит средний острый", "section": "treatment", "text": "Амоксициллин 1 г"}]
    sys, usr = build_prompt("чем лечить острый средний отит", chunks)
    assert "не переноси" in usr.lower()
    assert "Сопоставь данные из разных документов" not in usr
    assert "не переноси" in sys.lower()
