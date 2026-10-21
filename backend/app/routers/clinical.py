"""Клинические инструменты: дозы, совместимость, шкалы, разбор схем."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..clinical import normalize_drug, parse_frequency, parse_regimen
from ..core.config import DISCLAIMER
from ..core.deps import auth
from ..features import differential_diagnosis as dd
from ..features import dosage_calculator as dose
from ..knowledge_base import repository as repo
from ..rag.generator import vs

router = APIRouter(tags=["clinical"])


class DoseIn(BaseModel):
    weight_kg: float
    mg_per_kg: float
    max_mg: float | None = None
    frequency: str = ""


@router.post("/dosage")
def dosage(b: DoseIn):
    """Разовая доза по весу + суточная, если кратность распознана из строки
    («3 раза в сутки», «каждые 8 часов»). Разбор — детерминированный."""
    fq = parse_frequency(b.frequency)
    return {**dose.calc_dose(b.weight_kg, b.mg_per_kg, b.max_mg, b.frequency, fq["per_day"]),
            "frequency_parsed": fq, "disclaimer": DISCLAIMER}


class DiffIn(BaseModel):
    symptoms: list[str]


@router.post("/diff-diagnosis")
def diff(b: DiffIn):
    from ..core.red_flags import scan as red_scan
    return {"ranked": dd.rank(b.symptoms, repo.search_protocols(" ".join(b.symptoms)) or
        [{"nosology": d["nosology"], "title": d["title"], "icd10_codes": d["icd10_codes"],
          "sections": (repo.get_document(d["document_id"]) or {}).get("sections", {})}
         for d in repo.list_documents()]),
        "red_flags": red_scan(" ".join(b.symptoms)),
        "disclaimer": DISCLAIMER}


class DrugCheckIn(BaseModel):
    drugs: list[str]


@router.post("/drug-check")
def drug_check(b: DrugCheckIn, user: dict = Depends(auth)):
    """Предупреждения о совместимости строго по текстам протоколов, без домысливания.

    Названия приводятся к МКН по словарю (Флемоксин → Амоксициллин, Сумамед →
    Азитромицин): иначе поиск по бренду не находил предостережений, которые в
    протоколе написаны международным наименованием.
    """
    from ..features.drug_interactions import check_combination
    mapping = {d: normalize_drug(d) for d in b.drugs}
    canonical = list(dict.fromkeys(v for v in mapping.values() if v))
    res = check_combination(canonical, lambda d: vs().search(d, k=5))
    res["drugs_normalized"] = mapping
    res["disclaimer"] = DISCLAIMER
    return res


class RedFlagsIn(BaseModel):
    text: str = ""


@router.post("/red-flags")
def red_flags(b: RedFlagsIn):
    """Скрининг тревожных симптомов (Excellence-5): статичная таблица,
    LLM не используется. Не диагноз — повод срочно к врачу."""
    from ..core.red_flags import scan as red_scan
    return {"flags": red_scan(b.text), "disclaimer": DISCLAIMER}


class CentorIn(BaseModel):
    fever: bool = False
    exudate: bool = False
    nodes: bool = False
    no_cough: bool = False
    age_band: str = "15-44"


@router.post("/calculators/centor")
def calc_centor(b: CentorIn):
    """Шкала Centor/McIsaac (фарингит): чистая формула, без LLM."""
    from ..core import calculators as calc
    try:
        return {**calc.centor(b.fever, b.exudate, b.nodes, b.no_cough, b.age_band),
                "disclaimer": DISCLAIMER}
    except ValueError as e:
        raise HTTPException(400, str(e))


class PtaIn(BaseModel):
    thresholds_db: list[float]


@router.post("/calculators/pta")
def calc_pta(b: PtaIn):
    """Средний порог слуха PTA и степень потери (ВОЗ): чистая формула."""
    from ..core import calculators as calc
    try:
        return {**calc.pta(b.thresholds_db), "disclaimer": DISCLAIMER}
    except ValueError as e:
        raise HTTPException(400, str(e))


class RegimenIn(BaseModel):
    text: str


@router.post("/regimen/parse")
def regimen_parse(b: RegimenIn):
    """Детерминированный разбор схемы из текста протокола: препарат → МКН,
    доза, кратность, курс, путь введения. LLM не вызывается.

    Нужен там, где раньше приходилось читать текст глазами: проверка загруженной
    КР в админке, сверка схемы с чек-листом, подготовка структурированного
    ингеста (`diagnostics.*` сейчас пустые). Диапазоны берутся по нижней
    границе и помечаются флагом is_range — верхняя граница ведёт к передозу.
    """
    if not (b.text or "").strip():
        raise HTTPException(400, "Пустой текст")
    return {**parse_regimen(b.text[:5000]), "disclaimer": DISCLAIMER}
