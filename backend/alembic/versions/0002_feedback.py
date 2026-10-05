"""Add feedback table (Excellence: 👍/👎 оценки ответов)."""
from alembic import op
import sqlalchemy as sa
revision = "0002_feedback"
down_revision = "0001_init"
def upgrade():
    op.create_table("feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user", sa.String(), default="doctor"),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("vote", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(), default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True))
def downgrade():
    op.drop_table("feedback")
