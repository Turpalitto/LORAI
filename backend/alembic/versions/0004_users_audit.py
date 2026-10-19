"""users + audit_log: учётные записи в БД и журнал действий.

До этой миграции `USERS` собирался из env при старте процесса: добавить
врача можно было только правкой .env и рестартом, сменить пароль — тем же,
а ответить на вопрос «кто загрузил этот протокол» было нечем.

Миграция идемпотентна: таблицы создаются, только если их ещё нет (БД,
собранная тестовым create_all, уже содержит обе).
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_users_audit"
down_revision = "0003_query_log_user"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    tables = _tables()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("email", sa.String(), primary_key=True),
            sa.Column("pw_hash", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False, server_default="doctor"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("full_name", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
        )
    if "audit_log" not in tables:
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user", sa.String(), nullable=False, server_default=""),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("target", sa.String(), nullable=False, server_default=""),
            sa.Column("detail", sa.String(), nullable=False, server_default=""),
            sa.Column("ip", sa.String(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_audit_log_user", "audit_log", ["user"])
        op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade():
    tables = _tables()
    if "audit_log" in tables:
        op.drop_table("audit_log")
    if "users" in tables:
        op.drop_table("users")
