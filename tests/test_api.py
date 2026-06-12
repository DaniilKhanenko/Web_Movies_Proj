import importlib
import os
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


def make_app(tmp_path):
    os.environ["APP_DB_PATH"] = str(tmp_path / "test.db")
    os.environ["VIDEO_DIR"] = str(tmp_path / "video")
    Path(os.environ["VIDEO_DIR"]).mkdir()
    (Path(os.environ["VIDEO_DIR"]) / "movie.mp4").write_bytes(b"test video")

    import db.db
    import main

    importlib.reload(db.db)
    importlib.reload(main)
    return main.app


def test_auth_and_room_flow(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/register",
            json={"username": "alice", "password": "secret1"},
        )
        assert response.status_code == 200

        response = client.get("/api/me")
        assert response.status_code == 200
        assert response.json()["username"] == "alice"

        response = client.get("/api/movies")
        assert response.status_code == 200
        assert client.get("/api/videos").status_code == 404
        movie = response.json()["movies"][0]
        assert "stored_name" not in movie
        movie_id = movie["id"]

        response = client.post(
            "/api/rooms",
            json={
                "title": "Test room",
                "password": "roompass",
                "movie_id": movie_id,
                "room_id": "demo1",
            },
        )
        assert response.status_code == 200
        assert response.json()["id"] == "demo1"
        
        assert "movie_title" not in response.json()

        with client.websocket_connect("/ws/rooms/demo1") as websocket:
            message = websocket.receive_json()
            assert message["type"] == "room_state"


def test_wrong_room_password_is_rejected(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as owner:
        owner.post("/api/register", json={"username": "owner", "password": "secret1"})
        movie_id = owner.get("/api/movies").json()["movies"][0]["id"]
        owner.post(
            "/api/rooms",
            json={
                "title": "Room",
                "password": "goodpass",
                "movie_id": movie_id,
                "room_id": "demo2",
            },
        )

    with TestClient(app) as guest:
        guest.post("/api/register", json={"username": "guest", "password": "secret1"})
        response = guest.post("/api/rooms/demo2/join", json={"password": "badpass"})
        assert response.status_code == 403


def test_admin_can_upload_and_delete_movie(tmp_path):
    app = make_app(tmp_path)

    with TestClient(app) as client:
        response = client.post(
            "/api/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == 200
        assert response.json()["is_admin"] is True

        response = client.post(
            "/api/admin/movies",
            data={"title": "Uploaded"},
            files={"file": ("new.mp4", b"video bytes", "video/mp4")},
        )
        assert response.status_code == 200
        movie_id = response.json()["movie"]["id"]

        response = client.delete(f"/api/admin/movies/{movie_id}")
        assert response.status_code == 200


def test_rooms_schema_is_valid(tmp_path):
    # Создаём базу с уже актуальной схемой `rooms`,
    # чтобы проверить, что `init_db()` не ломается.
    db_path = tmp_path / "new.db"
    os.environ["APP_DB_PATH"] = str(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                stored_name TEXT NOT NULL UNIQUE,
                original_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                uploaded_by INTEGER,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE rooms (
                id TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                movie_id INTEGER NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            INSERT INTO users (username, password_hash, salt, is_admin, created_at)
            VALUES ('admin', 'hash', 'salt', 1, 1);
            INSERT INTO movies (title, stored_name, original_name, size_bytes, uploaded_by, created_at)
            VALUES ('Movie', 'movie.mp4', 'movie.mp4', 10, 1, 1);
            INSERT INTO rooms (id, owner_id, title, movie_id, password_hash, salt, created_at)
            VALUES ('r1', 1, 'Room', 1, 'hash', 'salt', 1);
            """
        )

    import db.db

    importlib.reload(db.db)
    db.db.init_db()

    with sqlite3.connect(db_path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(rooms)")]
        movie_id = connection.execute("SELECT movie_id FROM rooms WHERE id = 'r1'").fetchone()[0]

    assert movie_id == 1
