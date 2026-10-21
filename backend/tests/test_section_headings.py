"""Тесты разметки разделов по вёрстке (крупный кегль) и по строгому regex.

Зачем: раздел чанка — это то, на что опирается маршрутизация вопроса. Если
«Лечение» не распознано, вопрос про антибиотик ищет по определению и жалобам,
и модель честно отвечает «в контексте нет информации». Строгий regex требовал
совпадения всей строки и терял реальные главы («Медицинская реабилитация»,
«Клиническая картина»), поэтому заголовки, подтверждённые шрифтом, трактуются
мягче.

Чанкер выбрасывает сегменты короче 40 символов — в тестах тексты специально
длиннее, иначе проверялось бы не правило разметки, а порог длины.
"""
import fitz

BODY = "Клинический текст про заболевание, тактику ведения и наблюдение пациента. "
SHORT_BODY = "Обычный абзац про заболевание и его течение у взрослых."


# ------------------------------------------------------------------ чанкер
def test_typographic_heading_switches_section():
    """Заголовок, которого нет в строгом regex, но он крупнее текста."""
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1,
              "text": "Вступление\n" + BODY + "\n"
                      "Медицинская реабилитация\n" + BODY,
              "headings": ["Медицинская реабилитация"]}]
    chunks = build_index_chunks(pages)
    assert [c["section"] for c in chunks] == ["general", "treatment"]


def test_without_typography_strict_regex_still_works():
    """Текст без информации о шрифте (скан, txt) размечен по-прежнему."""
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1, "text": "Вступление\n" + SHORT_BODY + "\nЛечение\n" + BODY,
              "headings": []}]
    chunks = build_index_chunks(pages)
    assert [c["section"] for c in chunks] == ["general", "treatment"]


def test_heading_like_body_line_does_not_switch_section():
    """Строка «Лечение — назначает врач» не равна названию главы → остаётся текстом."""
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1, "text": "Вступление\n" + BODY + "\nЛечение — назначает врач.\n" + BODY,
              "headings": []}]
    chunks = build_index_chunks(pages)
    assert [c["section"] for c in chunks] == ["general"]


def test_latin_homoglyph_in_heading_is_tolerated():
    """В КР «Cимптомы, течение» набрано с латинской C — это реальный заголовок."""
    from app.ingestion.pipeline import _section_of_heading

    assert _section_of_heading("Cимптомы, течение") == "diagnostics"
    assert _section_of_heading("Симптомы, течение") == "diagnostics"


def test_references_heading_drops_bibliography():
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1,
              "text": "Лечение\n" + BODY + "\nИсточники и литература\n"
                      "1. Иванов И.И. Острый отит у взрослых. 2020. doi:10.1/x",
              "headings": ["Источники и литература"]}]
    chunks = build_index_chunks(pages)
    assert all("doi:" not in c["text"] for c in chunks)
    assert [c["section"] for c in chunks] == ["treatment"]


# --------------------------------------------------------------- приложения
def test_appendix_heading_gets_own_section():
    """«Приложение Б. Алгоритмы действий врача» — не продолжение главы.

    Регресс: приложения наследовали раздел последней главы и попадали в
    `definition`/`treatment` — на вопрос «чем лечить» в топ-6 приезжал
    «Состав рабочей группы» с бустом раздела лечения (109 чанков из 1073).
    """
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1,
              "text": "Лечение\n" + BODY + "\nПриложение Б. Алгоритмы действий врача\n" + BODY,
              "headings": ["Лечение", "Приложение Б. Алгоритмы действий врача"]}]
    chunks = build_index_chunks(pages)
    assert [c["section"] for c in chunks] == ["treatment", "appendix"]


def test_appendix_after_references_is_not_dropped():
    """Приложения идут после списка литературы: раздел `references` не должен их съесть."""
    from app.ingestion.pipeline import build_index_chunks

    pages = [{"page": 1,
              "text": "Источники и литература\n"
                      "1. Иванов И.И. Острый отит у взрослых. 2020. doi:10.1/x\n"
                      "Приложение А1. Состав рабочей группы по разработке\n" + BODY,
              "headings": ["Источники и литература"]}]
    chunks = build_index_chunks(pages)
    assert [c["section"] for c in chunks] == ["appendix"]


def test_appendix_letter_forms_match():
    """Реальные формы заголовков из КР: А1, А3.1, Б, В, Г1-ГN."""
    from app.ingestion.pipeline import _APPENDIX_HEADING

    for line in ("Приложение А1. Состав рабочей группы по разработке и",
                 "Приложение А2. Методология разработки клинических",
                 "Приложение А3.1 Расшифровка примечаний",
                 "Приложение Б. Алгоритмы действий врача",
                 "Приложение В. Информация для пациента",
                 "Приложение Г1-ГN. Шкалы оценки, вопросники и другие",
                 "Приложение Г2. Критерии контроля аллергического ринита"):
        assert _APPENDIX_HEADING.match(line), line


def test_reference_to_foreign_act_is_not_appendix():
    """«Приложение 3 приказа Минздрава» — ссылка на чужой документ, а не раздел КР.

    Проверено по корпусу: цифровая форма встречается только как ссылка на
    приказ, буквенная — только как заголовок приложения.
    """
    from app.ingestion.pipeline import _APPENDIX_HEADING

    for line in ("Приложение 3 приказа Минздрава России от 23.09.2020 № 1008н",
                 "Приложением 3 приказа Минздрава России",
                 "в соответствии с приложением А к приказу"):
        assert not _APPENDIX_HEADING.match(line), line


def test_appendix_text_does_not_leak_into_definition_section():
    """Текст приложения не должен попадать в `definition` карточки документа.

    Именно оттуда он уходил в LLM и в чек-лист: `sections.definition` на треть
    состоял из состава рабочей группы и методологии GRADE.
    """
    from app.ingestion.pipeline import build_index_chunks, _section_text

    pages = [{"page": 1,
              "text": "Определение\n" + BODY + "\n"
                      "Приложение А2. Методология разработки клинических\n"
                      "Целевая аудитория данных клинических рекомендаций: врачи-оториноларингологи.\n",
              "headings": ["Определение", "Приложение А2. Методология разработки клинических"]}]
    chunks = build_index_chunks(pages)
    assert "Целевая аудитория" not in _section_text(chunks, "definition")
    assert "Целевая аудитория" in _section_text(chunks, "appendix")


def test_appendix_never_gets_section_boost():
    """Маршрутизация вопроса не возвращает `appendix` — приложения не бустятся."""
    from app.rag.retriever import section_hint

    for q in ("как лечить острый отит", "что такое болезнь Меньера",
              "какие шкалы применяются", "алгоритм действий врача"):
        assert "appendix" not in section_hint(q), q


# ------------------------------------------------------------------ лоадер
def test_pdf_loader_marks_large_font_as_heading(tmp_path):
    """Реальный PDF: заголовок крупнее основного текста попадает в headings.

    Текст латиницей: базовые шрифты PyMuPDF не содержат кириллицы, а проверяется
    механика (кегль → заголовок), а не язык документа.
    """
    from app.ingestion.pdf_loader import load_pages

    body = "Clinical text about disease and management of the patient. " * 8
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(50, 50, 550, 400), body, fontsize=10)
    page.insert_text((50, 450), "Treatment", fontsize=18)
    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()

    pages = load_pages(str(path))
    assert pages[0]["headings"], "заголовок должен быть найден по кеглю"
    assert "Treatment" in pages[0]["headings"]
    assert not any("Clinical text" in h for h in pages[0]["headings"])


def test_pdf_loader_returns_headings_key_even_for_text_file(tmp_path):
    from app.ingestion.pdf_loader import load_pages

    p = tmp_path / "doc.txt"
    p.write_text("Определение\nТекст", encoding="utf-8")
    pages = load_pages(str(p))
    assert pages[0]["headings"] == []
    assert "Определение" in pages[0]["text"]


# ---------------------------------------------- маршрутизация вопроса (быстро)
def test_section_hint_covers_real_doctor_phrasings():
    """Врач пишет «чем лечить», а не «лечение»: форма глагола должна ловиться.

    Регресс был живым: запрос «чем лечить острый средний отит у взрослого?»
    получал пустой hint, и в выдачу шли чанки `definition` вместо лечения.
    """
    from app.rag.retriever import section_hint

    cases = {
        "чем лечить острый средний отит у взрослого?": "treatment",
        "как лечить ангину у ребёнка": "treatment",
        "какие антибиотики при отите": "treatment",
        "чем промывать нос при синусите": "treatment",
        "нужна ли операция при хроническом отите": "treatment",
        "какие симптомы у отита": "diagnostics",
        "дифференциальная диагностика оталгии": "diagnostics",
        "что такое болезнь Меньера": "definition",
        "профилактика рецидивирующего отита": "prevention",
        "когда госпитализировать при паратонзиллярном абсцессе": "referral_criteria",
    }
    for q, want in cases.items():
        assert section_hint(q) == [want], (q, section_hint(q), want)


def test_referral_wins_over_treatment_when_both_match():
    """«Госпитализировать» важнее «лечить»: узкая тема проверяется первой."""
    from app.rag.retriever import section_hint

    assert section_hint("стоит ли госпитализировать и как лечить абсцесс") == ["referral_criteria"]


def test_general_question_has_no_hint():
    from app.rag.retriever import section_hint

    assert section_hint("расскажи про отит") == []
