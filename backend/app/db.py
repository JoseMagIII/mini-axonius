from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import files

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.config import get_settings

READER_ROLE = "agent_reader"

# Each gap has a matching gap_<name> view.
GAPS = ("missing_edr", "vulnerable_software", "orphaned_owner", "ghost_assets")


def connect(**kwargs) -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url, row_factory=dict_row, **kwargs)


@contextmanager
def reader_connection() -> Iterator[psycopg.Connection]:
    """Connects as the SELECT-only role the agent uses, so writes fail even if the guardrail misses one."""
    settings = get_settings()
    conninfo = make_conninfo(settings.database_url, user=READER_ROLE, password=settings.reader_password)
    with psycopg.connect(conninfo, row_factory=dict_row, autocommit=True) as conn:
        yield conn


def init_db() -> None:
    """Creates tables, views, and the read-only role. Safe to run on every start."""
    schema = files("app.sql").joinpath("schema.sql").read_text()
    views = files("app.sql").joinpath("views.sql").read_text()
    password = get_settings().reader_password

    with connect(autocommit=True) as conn:
        conn.execute(schema)
        conn.execute(views)
        role = sql.Identifier(READER_ROLE)
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [READER_ROLE]).fetchone()
        action = "ALTER" if exists else "CREATE"
        conn.execute(sql.SQL(action + " ROLE {} LOGIN PASSWORD {}").format(role, sql.Literal(password)))
        conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '5s'").format(role))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(role))
        conn.execute(sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))


def query(statement: str, params: list | None = None) -> list[dict]:
    with connect() as conn:
        return conn.execute(statement, params).fetchall()
