"""Лёгкая обёртка: Chroma если есть, иначе TF-IDF in-memory + persist pickle."""
import os, pickle, math, re
from collections import Counter
def _tok(s: str) -> list[str]:
    return re.findall(r"[а-яa-z0-9]+", (s or "").lower())
class VectorStore:
    def __init__(self, persist_dir: str = "./data/vector_store"):
        self.dir = persist_dir; os.makedirs(persist_dir, exist_ok=True)
        self.chroma = None
        try:
            import chromadb
            self.chroma = chromadb.PersistentClient(path=persist_dir).get_or_create_collection("lorai")
        except Exception:
            self.chroma = None
        self.docs: list[dict] = []
        self._load()
    def _load(self):
        p = os.path.join(self.dir, "fallback.pkl")
        if os.path.exists(p) and self.chroma is None:
            try: self.docs = pickle.load(open(p, "rb"))
            except Exception: self.docs = []
    def _save(self):
        if self.chroma is None:
            pickle.dump(self.docs, open(os.path.join(self.dir, "fallback.pkl"), "wb"))
    def add(self, chunks: list[dict], doc_meta: dict):
        if self.chroma is not None:
            try:
                import uuid as _u
                ids = [str(_u.uuid4()) for _ in chunks]
                self.chroma.add(ids=ids,
                    documents=[c["text"][:4000] for c in chunks],
                    metadatas=[{**{k: str(v)[:300] for k, v in doc_meta.items()}, "section": c.get("section",""),
                                         "page_range": str(c.get("page_range",""))} for c in chunks])
                return
            except Exception: self.chroma = None
        for c in chunks:
            self.docs.append({"text": c["text"], **doc_meta, "section": c.get("section",""),
                              "page_range": c.get("page_range",[])})
        self._save()
    def search(self, query: str, k: int = 6, filters: dict | None = None) -> list[dict]:
        if self.chroma is not None:
            try:
                q = {"query_texts": [query], "n_results": k}
                if filters and filters.get("nosology"):
                    q["where"] = {"nosology": filters["nosology"]}
                r = self.chroma.query(**q)
                out = []
                for doc, meta, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0]):
                    score = max(0.0, 1.0 - float(dist) / 2.0)
                    out.append({"text": doc, "score": score, **meta})
                return out
            except Exception: pass
        # TF-IDF fallback (cosine)
        qt = Counter(_tok(query)); scores = []
        N = max(1, len(self.docs))
        df = Counter()
        toks_list = [_tok(d["text"]) for d in self.docs]
        for t in toks_list: df.update(set(t))
        def idf(w): return math.log(1 + N / (1 + df.get(w, 0)))
        qn = math.sqrt(sum((c*idf(w))**2 for w, c in qt.items())) or 1
        for d, tl in zip(self.docs, toks_list):
            if filters and filters.get("nosology") and d.get("nosology") != filters["nosology"]: continue
            if filters and filters.get("icd10"):
                if filters["icd10"] not in str(d.get("icd10_codes","")): continue
            ct = Counter(tl); dot = sum(qt[w]*ct[w]*(idf(w)**2) for w in qt if w in ct)
            dn = math.sqrt(sum((c*idf(w))**2 for w, c in ct.items())) or 1
            s = dot/(qn*dn)
            # небольшой буст за точное вхождение подстроки
            if query.lower()[:20] in d["text"].lower(): s = min(1.0, s + 0.25)
            scores.append({"text": d["text"], "score": round(float(s),4),
                           "document": d.get("title",""), "nosology": d.get("nosology",""),
                           "section": d.get("section",""), "page_range": d.get("page_range",[]),
                           "icd10_codes": d.get("icd10_codes",[])})
        return sorted(scores, key=lambda x: -x["score"])[:k]
