"""Apply database migrations at startup.

A database created by Phase 1 (tables made with create_all, no alembic_version) is
stamped as revision 0001 first, so upgrading never drops or re-creates user data.
A Postgres advisory lock keeps two processes from migrating at the same time.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from .db import get_engine

_LOCK_ID = 7_302_001
_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def _config() -> Config:
    cfg = Config(str(_INI))
    cfg.set_main_option("script_location", str(_INI.parent / "migrations"))
    return cfg


def run() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        is_pg = conn.dialect.name == "postgresql"
        if is_pg:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_ID})
        try:
            tables = set(inspect(conn).get_table_names())
            cfg = _config()
            if "alembic_version" not in tables and "users" in tables:
                command.stamp(cfg, "0001")
            command.upgrade(cfg, "head")
        finally:
            if is_pg:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_ID})
                conn.commit()


if __name__ == "__main__":
    run()
