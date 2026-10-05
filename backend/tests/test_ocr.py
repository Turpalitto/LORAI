"""OCR-слой: скан без движка не теряется тихо (PARTIAL без tesseract)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_scan_pdf(path: str):
    """PDF из одной картинки без текстового слоя (имитация скана)."""
    import fitz
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 200), "white")
    ImageDraw.Draw(img).line([(0, 0), (400, 200)], fill="black", width=5)
    tmp = path + ".png"
    img.save(tmp)
    doc = fitz.open()
    page = doc.new_page(width=400, height=200)
    page.insert_image(page.rect, filename=tmp)
    doc.save(path)
    doc.close()
    os.remove(tmp)


def test_scan_without_ocr_engine_marks_failed(tmp_path):
    from app.ingestion import pdf_loader
    from app.ingestion.pipeline import process_pdf
    from app.llm_clients.mock import MockLLMClient
    p = str(tmp_path / "scan.pdf")
    _make_scan_pdf(p)
    pages = pdf_loader.load_pages(p)
    assert pages and len(pages[0]["text"].strip()) < 50  # OCR-движка нет — текста нет
    doc = process_pdf(p, MockLLMClient(), title="Скан без OCR")
    assert doc["processing_status"] == "failed"
    assert doc["needs_manual_review"] is True  # тихой потери нет
