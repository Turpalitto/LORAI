"""query_log.user: разделение истории запросов по пользователю.

До этой миграции таблица не знала, кто задал вопрос, и `GET /history`
возвращал запросы всей клиники любому аутентифицированному врачу.

Миграция идемпотентна: на БД, созданной через `Base.metadata.create_all`
(там колонка уже есть), повторное добавление пропускается — иначе
`alembic upgrade head` падал бы на «duplicate column name».
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_query_log_user"
down_revision = "0002_feedback"


def _has_column(table: str, column: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    if not _has_column("query_log", "user"):
        op.add_column("query_log", sa.Column("user", sa.String(), nullable=True))
        # старые записи не знают автора — помечаем явно, а не угадываем
        op.execute("UPDATE query_log SET \"user\" = 'legacy' WHERE \"user\" IS NULL")
    insp = sa.inspect(op.get_bind())
    indexes = {i["name"] for i in insp.get_indexes("query_log")}
    if "ix_query_log_user" not in indexes:
        op.create_index("ix_query_log_user", "query_log", ["user"])


def downgrade():
    if _has_column("query_log", "user"):
        op.drop_index("ix_query_log_user", table_name="query_log")
        op.drop_column("query_log", "user")
