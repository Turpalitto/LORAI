"""CLI индексации: python scripts/ingest_pdf.py <pdf|dir>"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.ingestion.pipeline import process_pdf
from app.knowledge_base import repository as repo
from app.knowledge_base.vector_store import VectorStore
from app.llm_clients.mock import MockLLMClient
def ingest(path: str, title=None):
    doc = process_pdf(path, MockLLMClient(), title=title)
    repo.save_document(doc)
    VectorStore().add(doc["_chunks"], {"title": doc["title"], "nosology": doc["nosology"],
        "document": doc["title"], "icd10_codes": ",".join(doc["icd10_codes"])})
    print(f"OK {doc['title'][:60]} | ICD={doc['icd10_codes'][:6]} | conf={doc['extraction_confidence']} | chunks={len(doc['_chunks'])}")
    return doc
if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "./data/raw_pdfs"
    paths = [os.path.join(target, f) for f in os.listdir(target)] if os.path.isdir(target) else [target]
    # поддержка папки с кириллицей: ищем рекурсивно pdf
    import pathlib
    if os.path.isdir(target):
        paths = [str(p) for p in pathlib.Path(target).rglob("*.pdf")]
    for p in paths:
        try: ingest(p)
        except Exception as e: print(f"FAIL {p}: {e}")
