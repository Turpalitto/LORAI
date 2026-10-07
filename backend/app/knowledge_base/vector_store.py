"""Векторный поиск: embeddings (sentence-transformers), Chroma или TF-IDF.

Бэкенд выбирается явно через VECTOR_BACKEND:
  * `embeddings` — локальная мультиязычная модель (EMBEDDING_MODEL, по умолчанию
    intfloat/multilingual-e5-base). Решает главную проблему лексического TF-IDF
    на русском: «отита» и «отит» — разные токены, падежи не совпадают.
  * `chroma` — ChromaDB (исторический путь; без своего embedding_function
    использует англоязычную MiniLM и на русских КР проигрывает, см. DECISIONS #20).
  * `tfidf` — лексический fallback без внешних зависимостей (значение по умолчанию:
    работает всегда, даже если модель не скачана).

Если выбранные embeddings недоступны (нет пакета/модели), стор честно
откатывается на TF-IDF и сообщает причину в backend_note — молчаливой деградации нет.
"""
import os, pickle, math, re
from collections import Counter

import numpy as np


def _tok(s: str) -> list[str]:
    return re.findall(r"[а-яa-z0-9]+", (s or "").lower())


class VectorStore:
    def __init__(self, persist_dir: str = "./data/vector_store"):
        self.dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        # .env читает pydantic-settings, поэтому недостаточно os.getenv:
        # иначе VECTOR_BACKEND=embeddings из .env просто игнорировался.
        self.requested_backend = (os.getenv("VECTOR_BACKEND") or _settings_value("VECTOR_BACKEND", "tfidf")).strip().lower()
        self.backend = self.requested_backend
        self.backend_note = ""
        self.model_name = os.getenv("EMBEDDING_MODEL", "") or _default_model()
        self.chroma = None
        self._model = None
        self._prefix_q, self._prefix_p = "", ""
        self._vectors: np.ndarray | None = None  # (N, D), L2-нормированные

        if self.requested_backend == "chroma":
            try:
                import chromadb
                self.chroma = chromadb.PersistentClient(path=persist_dir).get_or_create_collection("lorai")
            except Exception as e:
                self.chroma = None
                self.backend, self.backend_note = "tfidf", f"chroma недоступна: {e}"
        elif self.requested_backend == "embeddings":
            self._init_embeddings()

        self.docs: list[dict] = []
        self._toks: list[list[str]] = []
        self._df: Counter = Counter()
        self._load()

    # ---------- инициализация бэкендов ----------
    def _init_embeddings(self) -> None:
        # HF-кэш направляем в проект ДО импорта huggingface_hub: иначе он пишет
        # в ~/.cache/huggingface, куда в песочнице нет доступа (и стенд не
        # самодостаточен). HF_HOME читается на импорте библиотеки.
        cache = _cache_dir()
        os.environ.setdefault("HF_HOME", cache)
        os.environ.setdefault("HF_HUB_CACHE", os.path.join(cache, "hub"))
        os.environ.setdefault("HF_XET_CACHE", os.path.join(cache, "xet"))
        os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", cache)
        try:
            from sentence_transformers import SentenceTransformer
            self._device = _pick_device()
            self._model = SentenceTransformer(self.model_name, cache_folder=cache, device=self._device)
            self.backend = "embeddings"
            # e5-модели требуют префиксы «query:»/«passage:» — без них качество падает.
            if "e5" in self.model_name.lower():
                self._prefix_q, self._prefix_p = "query: ", "passage: "
        except Exception as e:  # нет пакета/модели/памяти — честный откат
            self.backend = "tfidf"
            self.backend_note = f"embeddings недоступны ({type(e).__name__}: {str(e)[:120]}) — используется TF-IDF"

    def reindex_embeddings(self, force: bool = True) -> int:
        """Пересчитать векторы для всех документов (шаг переиндексации).
        Возвращает число проиндексированных чанков; без активных эмбеддингов — ошибка."""
        if self.backend != "embeddings" or self._model is None:
            raise RuntimeError(self.backend_note or "бэкенд эмбеддингов не активен")
        if force:
            self._vectors = None
        self._ensure_vectors()
        self._save_vectors()
        return 0 if self._vectors is None else int(len(self._vectors))

    def backend_name(self) -> str:
        if self.backend == "embeddings":
            return f"embeddings [{self.model_name}]"
        if self.backend_note:
            return f"tfidf (лексический; {self.backend_note[:60]})"
        if self.chroma is not None and self.backend == "chroma":
            return "chroma (default embedding function)"
        return "tfidf (лексический)"

    def stats(self) -> dict:
        """Состояние поиска для /health и дашборда. Векторы не грузим в память
        ради метрики: число берём из sidecar-файла рядом с индексом."""
        indexed = int(0 if self._vectors is None else len(self._vectors))
        if not indexed:
            try:
                import json as _json
                meta = _json.load(open(self._vec_meta_path(), encoding="utf-8"))
                if meta.get("model") == self.model_name:
                    indexed = int(meta.get("count", 0))
            except Exception:
                indexed = 0
        return {
            "backend": self.backend_name(),
            "requested": self.requested_backend,
            "chunks": len(self.docs),
            "vectors_indexed": indexed,
            "note": self.backend_note,
        }

    # ---------- TF-IDF кэш ----------
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

    # ---------- эмбеддинги ----------
    def _encode(self, texts: list[str], passage: bool) -> np.ndarray:
        pref = self._prefix_p if passage else self._prefix_q
        vecs = self._model.encode([pref + t for t in texts], batch_size=32,
                                  normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    def _vec_path(self) -> str:
        return os.path.join(self.dir, "embeddings.pkl")

    def _ensure_vectors(self) -> None:
        """Векторы для всех документов; при рассинхроне — переиндексация."""
        if self._vectors is not None and len(self._vectors) == len(self.docs):
            return
        p = self._vec_path()
        if os.path.exists(p):
            try:
                blob = pickle.load(open(p, "rb"))
                if (blob.get("model") == self.model_name
                        and len(blob.get("vectors", [])) == len(self.docs)):
                    self._vectors = np.asarray(blob["vectors"], dtype=np.float32)
                    return
            except Exception:
                pass
        self._vectors = self._encode([d["text"] for d in self.docs], passage=True) if self.docs else None
        self._save_vectors()

    def _vec_meta_path(self) -> str:
        return os.path.join(self.dir, "embeddings.meta.json")

    def _save_vectors(self) -> None:
        if self._vectors is None:
            return
        try:
            pickle.dump({"model": self.model_name, "vectors": self._vectors},
                        open(self._vec_path(), "wb"))
            import json as _json
            _json.dump({"model": self.model_name, "count": int(len(self._vectors))},
                       open(self._vec_meta_path(), "w", encoding="utf-8"))
        except Exception:
            pass

    # ---------- загрузка/сохранение ----------
    def _load(self):
        p = os.path.join(self.dir, "fallback.pkl")
        if os.path.exists(p) and self.chroma is None:
            try: self.docs = pickle.load(open(p, "rb"))
            except Exception: self.docs = []
        self._index_all()

    def _save(self):
        if self.chroma is None:
            pickle.dump(self.docs, open(os.path.join(self.dir, "fallback.pkl"), "wb"))

    # ---------- запись ----------
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
        new_docs = [{"text": c["text"], **doc_meta, "section": c.get("section",""),
                     "page_range": c.get("page_range",[])} for c in chunks]
        self.docs.extend(new_docs)
        self._index_all()
        if self.backend == "embeddings":
            if self._vectors is not None and len(self._vectors) == len(self.docs) - len(new_docs):
                fresh = self._encode([d["text"] for d in new_docs], passage=True)
                self._vectors = np.vstack([self._vectors, fresh])
            else:
                self._vectors = None  # пересоберём целиком при первом поиске
            self._save_vectors()
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
        self._vectors = None
        if self.backend == "embeddings" and self.docs:
            self._ensure_vectors()
        self._save()
        return removed

    # ---------- поиск ----------
    def search(self, query: str, k: int = 6, filters: dict | None = None,
               section_boost: list[str] | None = None,
               general_cap: int | None = None) -> list[dict]:
        """`section_boost` — разделы, которым отдаём приоритет при ранжировании
        (см. rag/retriever.section_hint). Буст влияет только на порядок: в поле
        score остаётся честное сходство, иначе гейт отказа начинал бы врать.

        `general_cap` — сколько «обзорных» чанков (section=general) допустимо в
        топ-k, когда вопрос явно про раздел. Без ограничения топ забивается
        дублями: general — 1304 из 1599 чанков корпуса, и нужный раздел до
        модели не доезжает (замер: docs/RETRIEVAL_EVAL.md)."""
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
        cap = general_cap if general_cap is not None else _general_cap()
        if self.backend == "embeddings" and self._model is not None and self.docs:
            try:
                return self._search_embeddings(query, k, filters, section_boost, cap)
            except Exception as e:
                self.backend_note = f"поиск по эмбеддингам упал ({e}) — TF-IDF"
                self.backend = "tfidf"
        return self._search_tfidf(query, k, filters, section_boost, cap)

    @staticmethod
    def _diversify(ranked: list[dict], k: int, general_cap: int | None,
                   section_boost: list[str] | None) -> list[dict]:
        """Ограничить долю обзорных чанков, когда раздел известен.
        Правило включается только при section_boost: для общих вопросов поведение
        прежнее (иначе теряли бы полноту ответа)."""
        cap = general_cap if section_boost else None
        out: list[dict] = []
        general_used = 0
        for c in ranked:
            if cap is not None and c.get("section") == "general":
                if general_used >= cap:
                    continue
                general_used += 1
            out.append(c)
            if len(out) >= k:
                break
        return out

    def _boost_factor(self, chunk: dict, section_boost: list[str] | None) -> float:
        if not section_boost:
            return 1.0
        return _section_boost() if chunk.get("section") in section_boost else 1.0

    def _tfidf_cosines(self, query: str) -> np.ndarray:
        """Лексическая близость каждого чанка к запросу (TF-IDF косинус).
        Нужна для гибридного ранжирования: эмбеддинги путают клинически
        соседние темы (острый/хронический отит, ринит/полипы), а точный термин
        в запросе («перегородка», «хронический») ловится лексикой."""
        if len(self._toks) != len(self.docs):
            self._index_all()
        qt = Counter(_tok(query))
        idf = self._idf
        def w_idf(w): return idf.get(w, math.log(1 + max(1, len(self.docs))))
        qn = math.sqrt(sum((c * w_idf(w)) ** 2 for w, c in qt.items())) or 1
        out = np.zeros(len(self.docs), dtype=np.float32)
        for i, (ct, dn) in enumerate(zip(self._ctrs, self._norms)):
            dot = sum(qt[w] * ct[w] * (w_idf(w) ** 2) for w in qt if w in ct)
            out[i] = dot / (qn * dn)
        return out

    def _search_embeddings(self, query: str, k: int, filters: dict | None,
                           section_boost: list[str] | None = None,
                           general_cap: int | None = None) -> list[dict]:
        if not (query or "").strip():
            return []
        self._ensure_vectors()
        if self._vectors is None:
            return []
        qv = self._encode([query], passage=False)[0]
        sims = self._vectors @ qv
        hybrid = _hybrid_weight()
        if hybrid > 0:
            # ранжируем по смеси, но врачу и гейту отказа показываем честный косинус
            sims = sims + hybrid * self._tfidf_cosines(query)
        if section_boost:
            factor = _section_boost()
            rank = np.array([float(s) * (factor if self.docs[i].get("section") in section_boost else 1.0)
                             for i, s in enumerate(sims)], dtype=np.float32)
        else:
            rank = sims
        order = np.argsort(-rank)
        out = []
        # берём с запасом: часть кандидатов отсеет ограничение на general
        pool = max(k, k * 4)
        for i in order:
            d = self.docs[int(i)]
            if filters and filters.get("nosology") and d.get("nosology") != filters["nosology"]:
                continue
            if filters and filters.get("icd10") and filters["icd10"] not in str(d.get("icd10_codes", "")):
                continue
            out.append({"text": d["text"], "score": round(float(sims[int(i)]), 4),
                        "document": d.get("title", ""), "nosology": d.get("nosology", ""),
                        "section": d.get("section", ""), "page_range": d.get("page_range", []),
                        "icd10_codes": d.get("icd10_codes", [])})
            if len(out) >= pool:
                break
        return self._diversify(out, k, general_cap, section_boost)

    def _search_tfidf(self, query: str, k: int, filters: dict | None,
                      section_boost: list[str] | None = None,
                      general_cap: int | None = None) -> list[dict]:
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
            raw = round(float(s), 4)
            scores.append((raw * self._boost_factor(d, section_boost),
                           {"text": d["text"], "score": raw,
                            "document": d.get("title",""), "nosology": d.get("nosology",""),
                            "section": d.get("section",""), "page_range": d.get("page_range",[]),
                            "icd10_codes": d.get("icd10_codes",[])}))
        scores.sort(key=lambda x: -x[0])
        return self._diversify([item for _, item in scores], k, general_cap, section_boost)


def _settings_value(name: str, default):
    try:
        from ..core.config import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _default_model() -> str:
    try:
        from ..core.config import settings
        return settings.EMBEDDING_MODEL
    except Exception:
        return "intfloat/multilingual-e5-base"


def _section_boost() -> float:
    """Во сколько раз поднять чанк нужного раздела при ранжировании."""
    try:
        return float(os.getenv("SECTION_BOOST", "") or _settings_boost())
    except Exception:
        return 1.15


def _settings_boost() -> float:
    from ..core.config import settings
    return float(getattr(settings, "SECTION_BOOST", 1.15))


def _hybrid_weight() -> float:
    """Вес лексической составляющей в гибридном ранжировании (0 — только эмбеддинги)."""
    try:
        from ..core.config import settings
        return float(os.getenv("HYBRID_WEIGHT", "") or getattr(settings, "HYBRID_WEIGHT", 0.0))
    except Exception:
        return 0.0


def _general_cap() -> int:
    """Сколько обзорных чанков пускать в топ при известном разделе."""
    try:
        from ..core.config import settings
        return int(os.getenv("GENERAL_CHUNK_CAP", "") or getattr(settings, "GENERAL_CHUNK_CAP", 2))
    except Exception:
        return 2


def _pick_device() -> str:
    """MPS (Apple) / CUDA / CPU. Кодирование запроса на CPU добавляет секунды,
    поэтому устройство выбираем явно; EMBEDDING_DEVICE перекрывает выбор."""
    pref = os.getenv("EMBEDDING_DEVICE", "").strip()
    if pref:
        return pref
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _cache_dir() -> str:
    """Каталог кэша модели: внутри проекта (см. EMBEDDING_CACHE_DIR)."""
    try:
        from ..core.config import settings
        path = settings.EMBEDDING_CACHE_DIR
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "hf_cache")
