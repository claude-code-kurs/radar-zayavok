"""Работа с базой заявок."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "radar.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_requests():
    """Все заявки для ленты кабинета, сначала самые свежие."""
    conn = connect()
    try:
        return conn.execute(
            """
            SELECT id, text, author, source, created_at
            FROM requests
            ORDER BY created_at DESC
            """
        ).fetchall()
    finally:
        conn.close()
