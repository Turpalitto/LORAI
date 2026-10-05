from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Text, JSON, Boolean, DateTime
from datetime import datetime
class Base(DeclarativeBase): pass
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String)
    nosology: Mapped[str] = mapped_column(String, index=True)
    icd10_codes: Mapped[list] = mapped_column(JSON, default=list)
    approval_year: Mapped[int] = mapped_column(Integer, default=2024)
    revision_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="processed")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    full_text: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String, default="medium")
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class QueryLog(Base):
    __tablename__ = "query_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String, default="")
    refused: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String, default="doctor")
    doc_id: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, default="")
