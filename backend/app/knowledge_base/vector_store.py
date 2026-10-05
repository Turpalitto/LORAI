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
        self._toks: list[list[str]] = []
        self._df: Counter = Counter()
        self._load()

    def _index_all(self):
        """Пересборка кэша: токены, df, счётчики и нормы документов.
        O(N·L) один раз при load/add/delete; запрос — O(N·|q|)."""
        self._toks = [_tok(d["text"]) for d in self.docs]
        self._df = Counter()
        for t in self._toks:
            self._df.update(set(t))
        N = max(1, len(self.docs))
        idf = {w: math.log(1 + N / (1 + c)) for w, c in self._df.items()}
        self._idf = idf
        self._ctrs = []
        self._norms = []
        for t in self._toks:
            c = Counter(t)
            self._ctrs.append(c)
            self._norms.append(math.sqrt(sum((v * idf[w]) ** 2 for w, v in c.items())) or 1)

    def _load(self):
        p = os.path.join(self.dir, "fallback.pkl")
        if os.path.exists(p) and self.chroma is None:
            try: self.docs = pickle.load(open(p, "rb"))
            except Exception: self.docs = []
        self._index_all()
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
        self._index_all()
        self._save()

    def delete_by_document(self, title: str) -> int:
        """Удаляет все чанки документа. Возвращает число удалённых.
        Нужен дедупу при повторной загрузке: старые векторы иначе остаются."""
        removed = 0
        if self.chroma is not None:
            try:
                self.chroma.delete(where={"document": title})
                removed = -1  # chroma не сообщает число; маркер «выполнено»
            except Exception:
                pass
        before = len(self.docs)
        self.docs = [d for d in self.docs
                     if d.get("document") != title and d.get("title") != title]
        removed = before - len(self.docs) if removed == 0 else removed
        self._index_all()
        self._save()
        return removed
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
        # TF-IDF fallback (cosine). Токены, idf и нормы предвычислены
        # в _index_all; на запрос — только скалярные произведения O(N·|q|).
        if len(self._toks) != len(self.docs):
            self._index_all()
        qt = Counter(_tok(query)); scores = []
        idf = self._idf
        def w_idf(w): return idf.get(w, math.log(1 + max(1, len(self.docs))))
        qn = math.sqrt(sum((c * w_idf(w)) ** 2 for w, c in qt.items())) or 1
        sub = query.lower()[:20].strip()
        for d, ct, dn in zip(self.docs, self._ctrs, self._norms):
            if filters and filters.get("nosology") and d.get("nosology") != filters["nosology"]: continue
            if filters and filters.get("icd10"):
                if filters["icd10"] not in str(d.get("icd10_codes","")): continue
            dot = sum(qt[w] * ct[w] * (w_idf(w) ** 2) for w in qt if w in ct)
            s = dot / (qn * dn)
            # небольшой буст за точное вхождение подстроки (только непустой запрос —
            # пустая строка входит в любой текст и раньше бустила все документы)
            if sub and sub in d["text"].lower(): s = min(1.0, s + 0.25)
            scores.append({"text": d["text"], "score": round(float(s),4),
                           "document": d.get("title",""), "nosology": d.get("nosology",""),
                           "section": d.get("section",""), "page_range": d.get("page_range",[]),
                           "icd10_codes": d.get("icd10_codes",[])})
        return sorted(scores, key=lambda x: -x["score"])[:k]
