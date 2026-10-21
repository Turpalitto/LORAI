"""Реранкер топ-N кандидатов кросс-энкодером.

Зачем: у e5 соседние нозологии идут в пределах 0.005 скора (острый/хронический
отит, ринит/полипы), и «правильный протокол, не тот раздел» — половина промахов.
Кросс-энкодер читает пару (вопрос, чанк) целиком и разделяет их лучше, чем
косинус по отдельным векторам.

Три правила, без которых реранкер приносит больше вреда, чем пользы:

1. **Только порядок.** Поле `score` остаётся честным косинусом: по нему работает
   порог отказа (`effective_threshold` + домен-гейт). Если подменить score на
   скор реранкера, гейт начнёт врать — ровно та же причина, по которой
   `section_boost` не меняет score.
2. **Мягкая деградация.** Модели нет / упала загрузка / OOM — возвращаем
   исходный порядок и пишем warning один раз. Поиск не должен падать из-за
   реранкера.
3. **Выключен по умолчанию.** Включается через `RERANK_BACKEND=cross` только
   после замера на hold-out: без цифр это «стало красивее», а не «стало точнее».

Замер: `scripts/eval_retrieval.py --rerank` (см. docs/RETRIEVAL_EVAL.md).
"""
from __future__ import annotations

import threading

from ..core.config import settings
from ..core.logging import log

_lock = threading.Lock()
_model = None
_failed = False


def enabled() -> bool:
    return (settings.RERANK_BACKEND or "off").strip().lower() in {"cross", "cross-encoder", "ce", "1", "true"}


def _load():
    """Ленивая загрузка модели: один раз, под замком, с кэшем внутри проекта."""
    global _model, _failed
    if _model is not None or _failed:
        return _model
    with _lock:
        if _model is not None or _failed:
            return _model
        try:
            from sentence_transformers import CrossEncoder

            _model = CrossEncoder(settings.RERANK_MODEL,
                                  cache_folder=settings.EMBEDDING_CACHE_DIR,
                                  max_length=512)
            log.info("реранкер загружен: %s", settings.RERANK_MODEL)
        except Exception as e:  # нет модели, нет сети, нет torch — не падаем
            _failed = True
            log.warning("реранкер недоступен (%s: %s) — порядок не меняется",
                        e.__class__.__name__, e)
        return _model


def _minmax(values: list[float]) -> list[float]:
    """Привести скоры к [0, 1] внутри набора кандидатов.

    Нужно, потому что косинус e5 живёт в узком диапазоне 0.78–0.90, а
    кросс-энкодер выдаёт логиты произвольного масштаба: складывать их напрямую
    нельзя — один член суммы подавит другой.
    """
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.5] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def rerank(query: str, chunks: list[dict], k: int | None = None) -> list[dict]:
    """Переупорядочить кандидатов. Возвращает не больше `k` (если задан).

    Хвост за пределами `RERANK_TOP_N` не оценивается и остаётся после
    переоценённых — реранкер не должен «выбрасывать» кандидатов, только
    переставлять.
    """
    if not chunks or not enabled():
        return chunks[:k] if k else chunks
    model = _load()
    if model is None:
        return chunks[:k] if k else chunks

    n = min(len(chunks), max(1, int(settings.RERANK_TOP_N)))
    pairs = [(query, (c.get("text") or "")[:1500]) for c in chunks[:n]]
    try:
        scores = model.predict(pairs, batch_size=int(settings.RERANK_BATCH),
                               show_progress_bar=False)
    except Exception as e:
        log.warning("реранкер упал на запросе (%s: %s) — порядок не меняется",
                    e.__class__.__name__, e)
        return chunks[:k] if k else chunks

    ce = [float(s) for s in scores]
    blend = min(1.0, max(0.0, float(settings.RERANK_BLEND)))
    if blend >= 1.0:
        order = sorted(range(n), key=lambda i: -ce[i])
    elif blend <= 0.0:
        order = list(range(n))  # реранкер включён, но вес нулевой — не трогаем
    else:
        # Смесь: ранг задаёт взвешенная сумма нормализованных скоров.
        # Косинус берём из честного score (он же уходит в гейт отказа).
        cos = [float(chunks[i].get("score") or 0.0) for i in range(n)]
        ce_n, cos_n = _minmax(ce), _minmax(cos)
        mixed = [blend * ce_n[i] + (1.0 - blend) * cos_n[i] for i in range(n)]
        order = sorted(range(n), key=lambda i: -mixed[i])

    out: list[dict] = []
    for i in order:
        c = dict(chunks[i])
        # score не трогаем (гейт отказа!), скор реранкера — только для отладки
        c["rerank_score"] = round(ce[i], 4)
        out.append(c)
    out.extend(chunks[n:])
    return out[:k] if k else out


def reset() -> None:
    """Сбросить кэш модели (тесты, смена RERANK_MODEL без рестарта)."""
    global _model, _failed
    with _lock:
        _model = None
        _failed = False
