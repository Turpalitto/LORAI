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
    # Кто спросил. До 1.3.1 колонки не было, и /history отдавал запросы всей
    # клиники любому вошедшему врачу. "guest" — запрос без токена.
    user: Mapped[str] = mapped_column(String, default="guest", index=True)
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
class User(Base):
    """Учётная запись. До 1.3.2 пользователи собирались в dict из env при
    старте: добавить врача = правка .env + рестарт, сменить пароль — то же,
    а кто загрузил протокол, не знал никто.

    `pw_hash` — PBKDF2-хеш (см. core/security.py), plaintext не хранится.
    Удаления нет: `active=False`, чтобы не терять авторство в аудите.
    """
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String, primary_key=True)
    pw_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="doctor")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    full_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    """Журнал действий: кто, что, с каким объектом, когда, с какого IP.

    Пишем только действия, меняющие состояние (вход, загрузка/правка
    протокола, управление пользователями), — не каждый GET, иначе журнал
    тонет в шуме. Тексты клинических запросов сюда не попадают.
    """
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String, default="", index=True)
    action: Mapped[str] = mapped_column(String, index=True)
    target: Mapped[str] = mapped_column(String, default="")
    detail: Mapped[str] = mapped_column(String, default="")
    ip: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    """Обратная связь 👍/👎 по ответам ассистента (Excellence-4: только сбор
    данных для анализа качества, модель \"на лету\" не меняется)."""
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user: Mapped[str] = mapped_column(String, default="doctor")
    query: Mapped[str] = mapped_column(Text)
    vote: Mapped[int] = mapped_column(Integer)  # +1 / -1
    comment: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
