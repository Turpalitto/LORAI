"""Постраничное извлечение текста. PyMuPDF основной, OCR fallback.

Кроме текста страница отдаёт `headings` — строки, которые вёрстка помечает как
заголовки (кегль заметно крупнее основного текста). Это нужно чанкеру: в КР
Минздрава главы набраны 17.5–20.2 pt при основном тексте 10.4–12 pt, и по
шрифту видно «Лечение» или «Клиническая картина» там, где строковая эвристика
видит обычный абзац («Медицинская реабилитация» — не «реабилитация»).
"""
from collections import Counter

# Кегль заголовка относительно основного текста. 1.25 — с запасом: подзаголовки
# в этих PDF идут 1.4–1.7×, а случайные крупные строки (колонтитул с датой)
# отсекаются длиной.
_HEADING_RATIO = 1.25
_HEADING_MAX_LEN = 120


def load_pages(path: str) -> list[dict]:
    # Не-PDF (txt/md) читаем как текст: PyMuPDF умеет «открыть» текстовый файл
    # и вернуть мохнатый текст (UTF-8 байты, прочитанные как latin-1). Раньше
    # протокол, загруженный .txt, попадал в индекс с битыми символами.
    if not _looks_like_pdf(path):
        return _read_as_text(path)
    try:
        import fitz
        try:
            doc = fitz.open(path)
        except Exception:
            # битый/пустой файл — не падаем, вернём то что можно прочитать как текст
            return _read_as_text(path)
        body = _body_size(doc)
        out = []
        for i, page in enumerate(doc):
            try:
                txt = page.get_text("text") or ""
            except Exception:
                txt = ""
            if len(txt.strip()) < 50:  # вероятный скан
                txt = _ocr_fallback(path, i, txt)
            try:
                heads = _page_headings(page, body)
            except Exception:
                heads = []
            out.append({"page": i + 1, "text": txt, "headings": heads})
        return out or [{"page": 1, "text": "", "headings": []}]
    except ImportError:
        return _read_as_text(path)
    except Exception:
        return _read_as_text(path)


def _looks_like_pdf(path: str) -> bool:
    """Настоящий ли это PDF: проверяем сигнатуру, а не расширение.

    Расширению верить нельзя (`.pdf`, внутри текст), а `fitz.open` на текстовом
    файле не падает — возвращает мусор.
    """
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except Exception:
        return False


def _body_size(doc) -> float:
    """Основной кегль документа: самый частый размер по числу символов.

    Считать «средний размер шрифта» нельзя: несколько крупных заголовков
    сдвинули бы порог, и обычный текст начал бы считаться заголовком.
    """
    chars: Counter = Counter()
    for page in doc:
        try:
            blocks = page.get_text("dict").get("blocks", [])
        except Exception:
            continue
        for b in blocks:
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text") or ""
                    if text.strip():
                        chars[round(float(span.get("size") or 0), 1)] += len(text)
    return float(chars.most_common(1)[0][0]) if chars else 0.0


def _page_headings(page, body_size: float) -> list[str]:
    """Строки страницы, набранные крупнее основного текста."""
    if body_size <= 0:
        return []
    out: list[str] = []
    for b in page.get_text("dict").get("blocks", []):
        for line in b.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(s.get("text") or "" for s in spans).strip()
            if not text or len(text) > _HEADING_MAX_LEN:
                continue
            size = max((float(s.get("size") or 0) for s in spans), default=0.0)
            if size >= body_size * _HEADING_RATIO:
                out.append(text)
    return out


def _read_as_text(path: str) -> list[dict]:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [{"page": 1, "text": f.read(), "headings": []}]
    except Exception:
        return [{"page": 1, "text": "", "headings": []}]


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
