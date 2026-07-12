from fastapi import Request

from .. import db


def get_db(request: Request):
    conn = db.get_conn(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()
