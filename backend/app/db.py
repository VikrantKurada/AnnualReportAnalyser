"""SQLite persistence layer: one file holds text, tables, facts, and vectors."""
import os
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def default_db_path() -> Path:
    return Path(os.environ.get("ARA_DB_PATH", "data/app.db"))


def get_conn(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    cur = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        tuple(values.values()),
    )
    conn.commit()
    return cur.lastrowid


def query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def update(conn: sqlite3.Connection, table: str, row_id: int, values: dict) -> None:
    sets = ", ".join(f"{k} = ?" for k in values)
    conn.execute(
        f"UPDATE {table} SET {sets} WHERE id = ?",
        (*values.values(), row_id),
    )
    conn.commit()
