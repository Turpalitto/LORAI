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
