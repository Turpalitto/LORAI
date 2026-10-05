"""Граф связей нозологий и детектор противоречий (Excellence-1).

related: связи по общим префиксам МКБ (J01/J32 — одна группа синуситов)
  и общим значимым токенам нозологий. Используется для блока
  «Похожие протоколы» в карточке нозологии.
contradictions: пары документов с пересекающимися кодами МКБ, у которых
  различаются числовые назначения (дозы/сроки) в treatment-секциях —
  система подсвечивает расхождение, а не молча выбирает источник.
"""
import re
from collections import Counter

from ..knowledge_base import repository as repo

_STOP = {
    "острый", "хронический", "клинические", "рекомендации", "россия",
    "меделемент", "взрослых", "ухо", "носа", "гортани",
}

_NUM_RX = re.compile(r"\d+(?:[.,]\d+)?\s*(?:мг|мл|г|мкг|МЕ|%|раз(?:а|ы)?(?:\s*в\s*(?:сутки|день))?|дн(?:ей|я)?|сут(?:ок|ки)?|нед(?:ель)?)", re.I)


def _tokens(s: str) -> set[str]:
    toks = set(re.findall(r"[а-яa-z]{4,}", (s or "").lower()))
    return {t for t in toks if t not in _STOP}


def _icd_prefixes(codes: list) -> set[str]:
    out = set()
    for c in codes or []:
        c = str(c).upper().strip()
        if len(c) >= 3:
            out.add(c[:3])
    return out


def related_protocols(doc_id: str, top: int = 5) -> list[dict]:
    docs = repo.list_documents()
    me = next((d for d in docs if d["document_id"] == doc_id), None)
    if not me:
        return []
    me_px = _icd_prefixes(me.get("icd10_codes"))
    me_toks = _tokens(me.get("nosology"))
    scored = []
    for d in docs:
        if d["document_id"] == doc_id:
            continue
        reasons = []
        shared_px = me_px & _icd_prefixes(d.get("icd10_codes"))
        if shared_px:
            reasons.append(f"общая группа МКБ: {', '.join(sorted(shared_px))}")
        shared_t = me_toks & _tokens(d.get("nosology"))
        if shared_t:
            reasons.append(f"общие термины: {', '.join(sorted(shared_t)[:3])}")
        if reasons:
            scored.append(
                {
                    "document_id": d["document_id"],
                    "title": d["title"],
                    "nosology": d["nosology"],
                    "icd10_codes": d.get("icd10_codes", []),
                    "reasons": reasons,
                    "score": len(shared_px) * 2 + len(shared_t),
                }
            )
    return sorted(scored, key=lambda x: -x["score"])[:top]


def _treatment_numbers(doc_id: str) -> Counter:
    full = repo.get_document(doc_id) or {}
    secs = full.get("sections") or {}
    t = secs.get("treatment", "")
    raw = t.get("raw", t) if isinstance(t, dict) else str(t)
    return Counter(m.group(0).lower() for m in _NUM_RX.finditer(raw or ""))


def find_contradictions() -> list[dict]:
    """Пары документов: общий код МКБ + различающиеся числовые назначения."""
    docs = repo.list_documents()
    out = []
    for i, a in enumerate(docs):
        for b in docs[i + 1:]:
            shared = set(map(str, a.get("icd10_codes", []))) & set(
                map(str, b.get("icd10_codes", []))
            )
            if not shared:
                continue
            na, nb = _treatment_numbers(a["document_id"]), _treatment_numbers(b["document_id"])
            if not na or not nb:
                continue
            only_a = sorted(set(na) - set(nb))[:5]
            only_b = sorted(set(nb) - set(na))[:5]
            if only_a or only_b:
                out.append(
                    {
                        "doc_a": {"document_id": a["document_id"], "title": a["title"]},
                        "doc_b": {"document_id": b["document_id"], "title": b["title"]},
                        "shared_icd": sorted(shared),
                        "only_in_a": only_a,
                        "only_in_b": only_b,
                        "note": "Числовые назначения в разделах лечения различаются — "
                        "сверьтесь с обоими протоколами. Решение принимает врач.",
                    }
                )
    return out
