import os
import sqlite3
from pathlib import Path

from db.models import TABLES

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("APP_DB_PATH", BASE_DIR / "app.db"))


def get_connection():
    connection = sqlite3.connect(DB_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as connection:
        for table_sql in TABLES:
            connection.execute(table_sql)
        connection.execute(
            """
            UPDATE movies
            SET title = COALESCE(NULLIF(title, ''), original_name, stored_name)
            WHERE title IS NULL OR title = ''
            """
        )
        
def fetch_one(query, params=()):
    with get_connection() as connection:
        return connection.execute(query, params).fetchone()


def fetch_all(query, params=()):
    with get_connection() as connection:
        return connection.execute(query, params).fetchall()


def execute(query, params=()):
    with get_connection() as connection:
        cursor = connection.execute(query, params)
        connection.commit()
        return cursor.lastrowid
