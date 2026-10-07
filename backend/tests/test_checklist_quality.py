"""Регресс-тесты генератора чек-листа.

Раньше при пустых структурированных разделах (а они пустые у всех 22 КР)
чек-лист собирался из «сырых» строк PDF: в пункты приёма попадали колонтитулы,
URL MedElement, даты печати и маркеры библиографии вида [13;15;16].
"""
from app.features.checklist_generator import build_checklist

DIRTY_RAW = """патологического процесса. Это связано с тем, что развивающаяся в
3/32 изолирует те или иные участки паратонзиллярного пространства
18.07.2025, 15:05
Паратонзиллярный абсцесс > Клинические рекомендации РФ 2024 (Россия) > MedElement
https://diseases.medelement.com/disease/паратонзиллярный-абсцесс/18330
Основными жалобами пациентов являются боль в горле и повышение температуры тела [13;15;16].
Лабораторные диагностические исследования Рекомендуется проведение общего (клинического) анализа крови всем пациентам с подозрением на абсцесс.
При отоскопии определяется гиперемия барабанной перепонки и выбухание в задних отделах.
"""


def _protocol(raw: str, **structured) -> dict:
    return {
        "nosology": "Тестовая нозология",
        "title": "Тестовая КР",
        "sections": {"diagnostics": {
            "complaints": structured.get("complaints", []),
            "anamnesis": [], "physical_exam": [], "lab_tests": [], "instrumental_tests": [],
            "raw": raw,
        }},
    }


def _points(result: dict) -> list[str]:
    return [p for b in result["checklist"] for p in b["points"]]


def test_no_pdf_furniture_in_points():
    r = build_checklist(_protocol(DIRTY_RAW))
    pts = _points(r)
    assert pts, "чек-лист не должен быть пустым при наличии текста"
    for p in pts:
        assert "http" not in p.lower()
        assert "MedElement" not in p
        assert ">" not in p
        assert "[13;15;16]" not in p
        assert not p.startswith("18.07.2025")
        assert not p.startswith("3/32")


def test_points_are_real_sentences():
    pts = _points(build_checklist(_protocol(DIRTY_RAW)))
    assert any("жалобами" in p for p in pts)
    assert all(len(p) >= 45 for p in pts)


def test_classification_into_visit_blocks():
    r = build_checklist(_protocol(DIRTY_RAW))
    blocks = {b["block"]: b["points"] for b in r["checklist"]}
    assert "Жалобы" in blocks
    assert "Лабораторно" in blocks
    assert "Осмотр" in blocks
    assert any("анализа крови" in p for p in blocks["Лабораторно"])
    assert r["auto_generated"] is True


def test_structured_sections_take_priority():
    r = build_checklist(_protocol(DIRTY_RAW, complaints=["Боль в горле", "Лихорадка"]))
    blocks = {b["block"]: b["points"] for b in r["checklist"]}
    assert blocks["Жалобы"] == ["Боль в горле", "Лихорадка"]
    assert r["auto_generated"] is False


def test_empty_text_is_honest():
    r = build_checklist(_protocol(""))
    assert r["checklist"] == []
    assert r["needs_source"] is True


def test_points_are_bounded_and_deduped():
    repeated = "\n".join(["Рекомендуется проведение общего анализа крови пациентам с подозрением на абсцесс."] * 5)
    pts = _points(build_checklist(_protocol(repeated)))
    assert len(pts) == 1
    long_line = "Рекомендуется " + "; ".join(f"шаг номер {i} с подробным описанием действий врача на приёме" for i in range(20))
    pts2 = _points(build_checklist(_protocol(long_line)))
    assert pts2 and all(len(p) <= 261 for p in pts2)
