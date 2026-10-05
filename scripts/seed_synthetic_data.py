"""Синтетические КР для теста пайплайна без реальных PDF (2 примера)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ingestion.pipeline import detect_sections, chunk_text
from app.knowledge_base import repository as repo
from app.knowledge_base.vector_store import VectorStore
import uuid
SYNTH = [
    {"nosology": "Острый средний отит", "icd": ["H66.9"],
     "text": "Определение\nОстрое воспаление среднего уха H66.9.\nДиагностика\nЖалобы: оталгия, лихорадка. Отоскопия: гиперемия барабанной перепонки.\nЛечение\nАмоксициллин 500 мг 3 раза в сутки 7 дней. Показания к госпитализации: мастоидит, парез лицевого нерва."},
    {"nosology": "Хронический тонзиллит", "icd": ["J35.0"],
     "text": "Определение\nХроническое воспаление нёбных миндалин J35.0.\nДиагностика\nЖалобы: дискомфорт в горле. Фарингоскопия: казеозные пробки.\nЛечение\nКонсервативно: промывание лакун. Операция: тонзиллэктомия при 4+ обострениях в год."},
]
for s in SYNTH:
    pages = [{"page": 1, "text": s["text"]}]
    secs = detect_sections(pages)
    doc = {"document_id": str(uuid.uuid4()), "title": f"SYNTH: {s['nosology']}", "nosology": s["nosology"],
        "icd10_codes": s["icd"], "approval_year": 2024, "revision_year": None,
        "source_file": "synthetic", "processing_status": "processed",
        "sections": {"definition": secs.get("definition",""), "diagnostics": {"raw": secs.get("diagnostics","")},
            "treatment": {"raw": secs.get("treatment","")}},
        "source_pages": secs.get("source_pages", {}), "extraction_confidence": "medium",
        "needs_manual_review": False,
        "_chunks": chunk_text(s["text"], {"section": "general", "page_range": [1]}),
        "_full_text": s["text"]}
    repo.save_document(doc)
    VectorStore().add(doc["_chunks"], {"title": doc["title"], "nosology": doc["nosology"],
        "document": doc["title"], "icd10_codes": ",".join(doc["icd10_codes"])})
    print("SEED OK:", doc["nosology"])
