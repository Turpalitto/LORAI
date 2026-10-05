"""Постраничное извлечение текста. PyMuPDF основной, OCR fallback."""
def load_pages(path: str) -> list[dict]:
    try:
        import fitz
        try:
            doc = fitz.open(path)
        except Exception:
            # битый/пустой файл — не падаем, вернём то что можно прочитать как текст
            return _read_as_text(path)
        out = []
        for i, page in enumerate(doc):
            try:
                txt = page.get_text("text") or ""
            except Exception:
                txt = ""
            if len(txt.strip()) < 50:  # вероятный скан
                txt = _ocr_fallback(path, i, txt)
            out.append({"page": i + 1, "text": txt})
        return out or [{"page": 1, "text": ""}]
    except ImportError:
        return _read_as_text(path)
    except Exception:
        return _read_as_text(path)


def _read_as_text(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [{"page": 1, "text": f.read()}]
    except Exception:
        return [{"page": 1, "text": ""}]

def _ocr_fallback(path: str, idx: int, txt: str) -> str:
    try:
        import fitz
        from PIL import Image
        import pytesseract, io
        doc = fitz.open(path)
        pix = doc[idx].get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        ocr = pytesseract.image_to_string(img, lang="rus+eng")
        return txt + "\n[OCR]\n" + ocr
    except Exception:
        return txt
