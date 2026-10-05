from pydantic import BaseModel
class ChatIn(BaseModel): query: str; k: int = 6; nosology: str | None = None; icd10: str | None = None
class DoseIn(BaseModel): weight_kg: float; mg_per_kg: float; max_mg: float | None = None; frequency: str = ""
class DiffIn(BaseModel): symptoms: list[str]
class RefIn(BaseModel): doc_id: str; answers: dict
class Login(BaseModel): email: str; password: str
class FavIn(BaseModel): doc_id: str; note: str = ""
