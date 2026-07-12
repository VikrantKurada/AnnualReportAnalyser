"""Token usage accounting per browser session and overall."""
import sqlite3
import time


def record_usage(conn: sqlite3.Connection, session_key: str, provider: str,
                 model: str, input_tokens: int, output_tokens: int,
                 context: str = "") -> None:
    conn.execute(
        "INSERT INTO token_usage (session_key, provider, model, input_tokens,"
        " output_tokens, context, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_key, provider, model, int(input_tokens or 0),
         int(output_tokens or 0), context, time.time()),
    )
    conn.commit()


def _totals(conn: sqlite3.Connection, where: str, params: tuple) -> dict:
    row = conn.execute(
        "SELECT COALESCE(SUM(input_tokens),0) i, COALESCE(SUM(output_tokens),0) o,"
        f" COUNT(*) c FROM token_usage {where}", params,
    ).fetchone()
    return {"input_tokens": row["i"], "output_tokens": row["o"], "calls": row["c"]}


def session_totals(conn: sqlite3.Connection, session_key: str) -> dict:
    return _totals(conn, "WHERE session_key = ?", (session_key,))


def totals_all(conn: sqlite3.Connection) -> dict:
    return _totals(conn, "", ())


def session_calls(conn: sqlite3.Connection, session_key: str, limit: int = 50) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM token_usage WHERE session_key = ? ORDER BY id DESC LIMIT ?",
        (session_key, limit),
    )]
