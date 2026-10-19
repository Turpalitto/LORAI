"""Схема БД: единственный источник правды — миграции Alembic.

Раньше `repository.py` делал `Base.metadata.create_all()` при импорте: схема
создавалась «как получится» из моделей, а миграции жили отдельно и никем не
применялись. На существующей БД create_all ничего не делает — новая колонка
появлялась только у того, кто вручную вспомнил про alembic. Теперь:

  * новая БД — `upgrade head` создаёт всё с нуля;
  * БД, созданная прежним create_all, сначала штампуется на последнюю
    «до-alembic» ревизию (0002), затем накатывается остаток;
  * тесты (`LORAI_TESTING=1`) по-прежнему собирают схему из моделей — это
    быстрее и не требует файла миграций.
"""
from __future__ import annotations

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from .config import settings

# Ревизия, соответствующая состоянию схемы, которое создавал create_all
# до перехода на миграции.
_LEGACY_REVISION = "0002_feedback"


def _backend_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _config() -> Config:
    backend = _backend_dir()
    cfg = Config(os.path.join(backend, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend, "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return cfg


def ensure_schema() -> str:
    """Приводит схему к head. Возвращает описание выполненного шага (для лога)."""
    eng = create_engine(settings.DATABASE_URL)
    try:
        if os.getenv("LORAI_TESTING") == "1":
            from ..knowledge_base.models import Base
            Base.metadata.create_all(eng)
            return "create_all (tests)"

        tables = set(inspect(eng).get_table_names())
        cfg = _config()
        if tables and "alembic_version" not in tables:
            # БД из эпохи create_all: помечаем известное состояние и катим остаток.
            command.stamp(cfg, _LEGACY_REVISION)
        command.upgrade(cfg, "head")
        return "alembic upgrade head"
    finally:
        eng.dispose()
