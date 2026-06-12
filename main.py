import mimetypes
import os
import re
import uuid
import secrets
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import (

    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi

from db.db import execute, fetch_all, fetch_one, init_db
from db.schemas import AuthData, RoomCreateData, RoomJoinData
from db.security import (
    SESSION_TTL_SECONDS,
    check_password,
    hash_password,
    make_salt,
    make_session_token,
    now,
    session_expires_at,
)

BASE_DIR = Path(__file__).resolve().parent
FRONT_DIR = BASE_DIR / "front"
VIDEO_DIR = Path(os.environ.get("VIDEO_DIR", BASE_DIR / "video"))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogg", ".ogv", ".mov"}

connections = {}


@asynccontextmanager
async def lifespan(app):
    init_db()
    VIDEO_DIR.mkdir(exist_ok=True)
    ensure_admin_user()
    sync_video_folder()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")

OPENAPI_TRANSLATIONS = {
    "/": {"get": {"summary": "Перенаправление на каталог", "description": "Перенаправляет на страницу каталога фильмов."}},
    "/login": {"get": {"summary": "Страница входа", "description": "Возвращает HTML-страницу для входа пользователя."}},
    "/catalog": {"get": {"summary": "Страница каталога", "description": "Возвращает HTML-страницу с каталогом фильмов."}},
    "/room/{room_id}": {"get": {"summary": "Страница комнаты", "description": "Страница комнаты для совместного просмотра фильма."}},
    "/admin": {"get": {"summary": "Админ-панель", "description": "Интерфейс администратора для управления фильмами."}},
    "/api/register": {"post": {"summary": "Регистрация пользователя", "description": "Регистрирует нового пользователя и создаёт сессию."}},
    "/api/login": {"post": {"summary": "Авторизация", "description": "Выполняет вход и создаёт сессию (cookie)."}},
    "/api/logout": {"post": {"summary": "Выход", "description": "Удаляет текущую сессию пользователя."}},
    "/api/me": {"get": {"summary": "Данные текущего пользователя", "description": "Возвращает имя пользователя и флаг администратора."}},
    "/api/movies": {"get": {"summary": "Список фильмов", "description": "Возвращает список доступных фильмов."}},
    "/api/admin/movies": {"post": {"summary": "Загрузка фильма (админ)", "description": "Загружает видеофайл в каталог (только для админов)."}},
    "/api/admin/movies/{movie_id}": {"delete": {"summary": "Удаление фильма (админ)", "description": "Удаляет фильм и файл из хранилища (только для админов)."}},
    "/api/rooms": {"post": {"summary": "Создать комнату", "description": "Создаёт новую комнату для совместного просмотра."}},
    "/api/rooms/{room_id}/join": {"post": {"summary": "Присоединиться к комнате", "description": "Присоединяется к комнате после проверки пароля."}},
    "/api/rooms/{room_id}": {"get": {"summary": "Информация о комнате", "description": "Возвращает данные комнаты и URL видео (требуется доступ)."}},
    "/video/{file_name}": {"get": {"summary": "Получить видео", "description": "Отдаёт видео. Поддерживает Range-запросы для потоковой передачи."}, "head": {"summary": "Метаданные видео", "description": "Возвращает заголовки и размер файла без тела."}},
}

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Сервис совместного просмотра",
        version="1.0.0",
        description="API для сервиса совместного просмотра видео",
        routes=app.routes,
    )
    paths = openapi_schema.get("paths", {})
    for path, path_item in paths.items():
        translation = OPENAPI_TRANSLATIONS.get(path)
        if not translation:
            continue
        for method, operation in path_item.items():
            method_lower = method.lower()
            trans = translation.get(method_lower) or translation.get("default")
            if not trans:
                continue
            if "summary" in trans:
                operation["summary"] = trans["summary"]
            if "description" in trans:
                operation["description"] = trans["description"]
            if "tags" in trans:
                operation["tags"] = trans["tags"]

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


@app.middleware("http")
async def add_security_headers(request, call_next):
    # Базовые HTTP-заголовки безопасности для всех страниц и API.
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


def row_to_dict(row):
    return dict(row) if row else None


def validate_username(username):
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="Username: 3-32 символа, латиница, цифры или _",
        )


def validate_password(password):
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Пароль минимум 6 символов")


def validate_room_password(password):
    if len(password) < 3:
        raise HTTPException(status_code=400, detail="Пароль комнаты минимум 3 символа")


def validate_room_id(room_id):
    if not ROOM_ID_RE.match(room_id):
        raise HTTPException(
            status_code=400,
            detail="ID комнаты: 4-32 символа, латиница, цифры, - или _",
        )


def get_user_by_session(token):
    if not token:
        return None

    row = fetch_one(
        """
        SELECT users.id, users.username, users.is_admin
        FROM sessions
        JOIN users ON users.id = sessions.user_id
        WHERE sessions.token = ? AND sessions.expires_at > ?
        """,
        (token, now()),
    )
    return row_to_dict(row)


def get_current_user(request):
    return get_user_by_session(request.cookies.get("session_token"))


def require_user(request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Нужно войти")
    return user


def require_admin(request):
    user = require_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Нужен админский аккаунт")
    return user


def set_session_cookie(response, user_id):
    # Сессия хранится в БД, а в cookie кладется только случайный токен.
    token = make_session_token()
    execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, session_expires_at()),
    )
    response.set_cookie(
        "session_token",
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
    )


def ensure_admin_user():
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        return

    user = row_to_dict(fetch_one("SELECT * FROM users WHERE username = ?", (ADMIN_USERNAME,)))
    if user:
        execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user["id"],))
        return

    salt = make_salt()
    user_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO users (id, username, password_hash, salt, is_admin, created_at)
        VALUES (?, ?, ?, ?, 1, ?)
        """,
        (user_id, ADMIN_USERNAME, hash_password(ADMIN_PASSWORD, salt), salt, now()),
    )


def clean_title(file_name):
    return Path(file_name).stem.replace("_", " ").replace("-", " ").strip() or file_name


def safe_upload_name(file_name):
    original = Path(file_name).name
    suffix = Path(original).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Поддерживаются только видеофайлы")

    base = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original).stem).strip("-") or "movie"
    return f"{base}-{secrets.token_hex(4)}{suffix}"


def get_safe_video_path(file_name):
    if "/" in file_name or "\\" in file_name:
        raise HTTPException(status_code=400, detail="Bad video file")

    file_path = VIDEO_DIR / file_name
    if file_path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Bad video format")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Video not found")

    return file_path


def movie_to_json(movie):
    movie = dict(movie)
    return {
        "id": movie["id"],
        "title": movie["title"],
        "original_name": movie["original_name"],
        "size_bytes": movie["size_bytes"],
        "video_url": f"/video/{movie['stored_name']}",
    }


def get_movie(movie_id):
    return row_to_dict(fetch_one("SELECT * FROM movies WHERE id = ?", (movie_id,)))


def list_movies():
    rows = fetch_all("SELECT * FROM movies ORDER BY created_at DESC, id DESC")
    movies = []

    for row in rows:
        movie = dict(row)
        if (VIDEO_DIR / movie["stored_name"]).exists():
            movies.append(movie_to_json(movie))

    return movies


def sync_video_folder():
    # Уже лежащие в папке video файлы автоматически добавляются в каталог.
    for file_path in sorted(VIDEO_DIR.iterdir()):
        if not file_path.is_file() or file_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        exists = fetch_one("SELECT id FROM movies WHERE stored_name = ?", (file_path.name,))
        if exists:
            continue

        movie_id = str(uuid.uuid4())
        execute(
            """
            INSERT INTO movies (id, title, stored_name, original_name, size_bytes, uploaded_by, created_at)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            """,
            (movie_id, clean_title(file_path.name), file_path.name, file_path.name, file_path.stat().st_size, now()),
        )


def generate_room_id():
    while True:
        room_id = secrets.token_urlsafe(6).replace("_", "-")[:8]
        if not fetch_one("SELECT id FROM rooms WHERE id = ?", (room_id,)):
            return room_id


def get_room(room_id):
    row = fetch_one(
        """
        SELECT rooms.*, movies.stored_name
        FROM rooms
        JOIN movies ON movies.id = rooms.movie_id
        WHERE rooms.id = ?
        """,
        (room_id,),
    )
    return row_to_dict(row)


def user_has_room_access(user_id, room_id):
    return fetch_one(
        "SELECT 1 FROM room_access WHERE user_id = ? AND room_id = ?",
        (user_id, room_id),
    ) is not None


def add_room_access(user_id, room_id):
    execute(
        """
        INSERT OR IGNORE INTO room_access (user_id, room_id, joined_at)
        VALUES (?, ?, ?)
        """,
        (user_id, room_id, now()),
    )


def room_to_json(room):
    return {
        "id": room["id"],
        "title": room["title"],
        "movie_id": room["movie_id"],
        "video_url": f"/video/{room['stored_name']}",
    }


def save_room_state(room_id, playing, position, rate):
    execute(
        """
        INSERT INTO room_states (room_id, playing, position, playback_rate, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(room_id) DO UPDATE SET
            playing = excluded.playing,
            position = excluded.position,
            playback_rate = excluded.playback_rate,
            updated_at = excluded.updated_at
        """,
        (room_id, int(playing), float(position), float(rate), time.time()),
    )

def get_room_state(room_id):
    row = fetch_one(
        "SELECT playing, position, playback_rate, updated_at FROM room_states WHERE room_id = ?",
        (room_id,),
    )

    if not row:
        return {"playing": False, "position": 0, "rate": 1.0, "updatedAt": time.time()}

    playing = bool(row["playing"])
    position = float(row["position"])
    rate = float(row["playback_rate"])
    updated_at = float(row["updated_at"])

    if playing:
        position += max(time.time() - updated_at, 0) * rate

    return {
        "playing": playing,
        "position": position,
        "rate": rate,
        "updatedAt": updated_at,
    }


def read_file_range(file_path, start, length, chunk_size=1024 * 1024):
    def open_shared_file(path):
        if os.name == "nt":
            import ctypes
            import msvcrt

            FILE_SHARE_READ = 1
            FILE_SHARE_WRITE = 2
            FILE_SHARE_DELETE = 4
            GENERIC_READ = 0x80000000
            OPEN_EXISTING = 3
            FILE_ATTRIBUTE_NORMAL = 0x80
            FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000

            handle = ctypes.windll.kernel32.CreateFileW(
                str(path),
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL | FILE_FLAG_SEQUENTIAL_SCAN,
                None,
            )

            if handle == -1 or handle == 0:
                raise OSError("CreateFileW failed")

            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            fd = msvcrt.open_osfhandle(handle, flags)
            return os.fdopen(fd, "rb")

        return open(path, "rb")

    # Видео отдается частями, чтобы браузер мог быстро начинать просмотр и перематывать.
    with open_shared_file(file_path) as video_file:
        video_file.seek(start)
        left = length

        while left > 0:
            chunk = video_file.read(min(chunk_size, left))
            if not chunk:
                break

            left -= len(chunk)
            yield chunk


async def broadcast(room_id, message):
    # В памяти храним только активные WebSocket-подключения текущего процесса.
    dead_connections = []

    for websocket in connections.get(room_id, set()):
        try:
            await websocket.send_json(message)
        except RuntimeError:
            dead_connections.append(websocket)

    for websocket in dead_connections:
        connections.get(room_id, set()).discard(websocket)


@app.get("/")
def index():
    return RedirectResponse("/catalog")


@app.get("/login")
def login_page():
    return FileResponse(FRONT_DIR / "login.html")


@app.get("/catalog")
def catalog_page():
    return FileResponse(FRONT_DIR / "catalog.html")


@app.get("/room/{room_id}")
def room_page(room_id: str):
    return FileResponse(FRONT_DIR / "room.html")


@app.get("/admin")
def admin_page():
    return FileResponse(FRONT_DIR / "admin.html")


@app.post("/api/register")
def register(data: AuthData, response: Response):
    username = data.username.strip()
    validate_username(username)
    validate_password(data.password)

    if fetch_one("SELECT id FROM users WHERE username = ?", (username,)):
        raise HTTPException(status_code=409, detail="Пользователь уже существует")

    salt = make_salt()
    user_id = str(uuid.uuid4())

    execute(
        """
        INSERT INTO users (id, username, password_hash, salt, is_admin, created_at)
        VALUES (?, ?, ?, ?, 0, ?)
        """,
        (user_id, username, hash_password(data.password, salt), salt, now()),
    )
    set_session_cookie(response, user_id)


@app.post("/api/login")
def login(data: AuthData, response: Response):
    row = fetch_one("SELECT * FROM users WHERE username = ?", (data.username.strip(),))
    user = row_to_dict(row)

    if not user or not check_password(data.password, user["password_hash"], user["salt"]):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    set_session_cookie(response, user["id"])
    return {"username": user["username"], "is_admin": bool(user["is_admin"])}



@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        execute("DELETE FROM sessions WHERE token = ?", (token,))

    response.delete_cookie("session_token")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    user = require_user(request)
    return {"username": user["username"], "is_admin": bool(user["is_admin"])}


@app.get("/api/movies")
def movies(request: Request):
    require_user(request)
    return {"movies": list_movies()}


@app.post("/api/admin/movies")
def upload_movie(
    request: Request,
    title: str = Form(""),
    file: UploadFile = File(...),
):
    user = require_admin(request)
    stored_name = safe_upload_name(file.filename or "movie.mp4")
    file_path = VIDEO_DIR / stored_name

    with file_path.open("wb") as output_file:
        shutil.copyfileobj(file.file, output_file)

    movie_title = title.strip()[:120] or clean_title(file.filename or stored_name)
    movie_id = str(uuid.uuid4())
    execute(
        """
        INSERT INTO movies (id, title, stored_name, original_name, size_bytes, uploaded_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            movie_id,
            movie_title,
            stored_name,
            Path(file.filename or stored_name).name,
            file_path.stat().st_size,
            user["id"],
            now(),
        ),
    )
    return {"movie": movie_to_json(get_movie(movie_id))}


@app.delete("/api/admin/movies/{movie_id}")
def delete_movie(movie_id: str, request: Request):
    require_admin(request)
    movie = get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")

    file_path = VIDEO_DIR / movie["stored_name"]
    
    if file_path.exists():
        import time
        success = False
        
        for _ in range(10):
            try:
                file_path.unlink()
                success = True
                break
            except PermissionError:
                time.sleep(0.5)
        
        if not success:
            raise HTTPException(
                status_code=400, 
                detail="Файл всё ещё скачивается в фоне. Обновите страницу (F5) и попробуйте снова."
            )

    execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    return {"ok": True}


@app.post("/api/rooms")
def create_room(data: RoomCreateData, request: Request):
    user = require_user(request)
    validate_room_password(data.password)

    movie = get_movie(data.movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Фильм не найден")
    get_safe_video_path(movie["stored_name"])

    title = data.title.strip()[:80] or movie["title"]
    room_id = data.room_id.strip() or generate_room_id()
    validate_room_id(room_id)

    if fetch_one("SELECT id FROM rooms WHERE id = ?", (room_id,)):
        raise HTTPException(status_code=409, detail="Комната с таким ID уже есть")

    salt = make_salt()
    execute(
        """
        INSERT INTO rooms
            (id, owner_id, title, movie_id, password_hash, salt, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            room_id,
            user["id"],
            title,
            movie["id"],
            hash_password(data.password, salt),
            salt,
            now(),
        ),
    )
    add_room_access(user["id"], room_id)
    save_room_state(room_id, False, 0, 1.0)

    return room_to_json(get_room(room_id))


@app.post("/api/rooms/{room_id}/join")
def join_room(room_id: str, data: RoomJoinData, request: Request):
    user = require_user(request)
    validate_room_id(room_id)

    room = get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if not check_password(data.password, room["password_hash"], room["salt"]):
        raise HTTPException(status_code=403, detail="Неверный пароль комнаты")

    add_room_access(user["id"], room_id)
    return room_to_json(room)


@app.get("/api/rooms/{room_id}")
def room_info(room_id: str, request: Request):
    user = require_user(request)
    validate_room_id(room_id)

    room = get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    if not user_has_room_access(user["id"], room_id):
        raise HTTPException(status_code=403, detail="Нет доступа к комнате")

    return room_to_json(room)


@app.get("/video/{file_name}")
def video(file_name: str, request: Request):
    file_path = get_safe_video_path(file_name)
    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if not range_header:
        # Отдаём через генератор, чтобы использовать открытие с общим доступом
        response = StreamingResponse(
            read_file_range(file_path, 0, file_size),
            status_code=200,
            media_type=content_type,
        )
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(file_size)
        return response

    # Браузер присылает Range при потоковом просмотре и перемотке.
    match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        raise HTTPException(status_code=416, detail="Bad range")

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    end = min(end, file_size - 1)

    if start >= file_size or start > end:
        raise HTTPException(status_code=416, detail="Bad range")

    length = end - start + 1
    response = StreamingResponse(
        read_file_range(file_path, start, length),
        status_code=206,
        media_type=content_type,
    )
    response.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    response.headers["Accept-Ranges"] = "bytes"
    response.headers["Content-Length"] = str(length)
    return response





@app.head("/video/{file_name}")
def video_head(file_name: str):
    file_path = get_safe_video_path(file_name)
    response = Response(status_code=200)
    response.headers["Content-Type"] = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    response.headers["Content-Length"] = str(file_path.stat().st_size)
    response.headers["Accept-Ranges"] = "bytes"
    return response


@app.websocket("/ws/rooms/{room_id}")
async def room_websocket(websocket: WebSocket, room_id: str):
    # WebSocket доступен только авторизованным пользователям с доступом к комнате.
    user = get_user_by_session(websocket.cookies.get("session_token"))
    if not user or not ROOM_ID_RE.match(room_id):
        await websocket.close(code=1008)
        return

    room = get_room(room_id)
    if not room or not user_has_room_access(user["id"], room_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    connections.setdefault(room_id, set()).add(websocket)
    await websocket.send_json({"type": "room_state", "state": get_room_state(room_id)})

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "player_event":
                continue

            action = data.get("action")
            if action not in {"play", "pause", "seek", "ratechange"}:
                continue

            try:
                position = max(float(data.get("position", 0)), 0)
            except (TypeError, ValueError):
                position = 0
                
            try:
                rate = float(data.get("rate", 1.0))
            except (TypeError, ValueError):
                rate = 1.0

            if action == "play":
                playing = True
            elif action == "pause":
                playing = False
            else:
                playing = bool(data.get("playing"))

            save_room_state(room_id, playing, position, rate)

            message = {
                "type": "player_event",
                "action": action,
                "playing": playing,
                "position": position,
                "rate": rate,
                "updatedAt": time.time(),
                "clientId": str(data.get("clientId", ""))[:80],
                "username": user["username"],
            }
            await broadcast(room_id, message)

    except WebSocketDisconnect:
        connections.get(room_id, set()).discard(websocket)
