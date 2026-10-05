from alembic import context
from sqlalchemy import create_engine
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.knowledge_base.models import Base
from app.core.config import settings
def run_migrations_online():
    eng = create_engine(settings.DATABASE_URL)
    with eng.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
run_migrations_online()
