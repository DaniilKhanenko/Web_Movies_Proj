# Video Room

Веб-приложение для совместного просмотра видео.

Стек:

- FastAPI
- SQLite
- HTML, CSS и JavaScript
- WebSocket

## Структура

```text
db/
  db.py
  models.py
  schemas.py
  security.py
front/
  login.html
  catalog.html
  room.html
  admin.html
  *.js
  styles.css
tests/
  test_api.py
main.py
Dockerfile
pyproject.toml
```

## Страницы

- `/login` - вход и регистрация.
- `/catalog` - каталог фильмов.
- `/room/{id}` - комната просмотра.
- `/admin` - загрузка и удаление фильмов.

## Админ

При первом запуске автоматически создается админ:

```text
login: admin
password: admin123
```

Пароль можно заменить переменной окружения:

```bash
set ADMIN_PASSWORD=your-password
```

Админ загружает фильмы через `/admin`. После загрузки фильм появляется в каталоге. Превью в каталоге создается автоматически в браузере из кадра видео.

## Видео

Файлы видео лежат в папке `video`.

Поддерживаются:

```text
.mp4, .webm, .ogg, .ogv, .mov
```

Уже существующие файлы из `video` автоматически попадают в каталог при запуске сервера.

## Запуск без Docker

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Запуск через Docker

PowerShell:

```powershell
docker build -t video-room .
docker run --rm -p 8000:8000 -v "${PWD}\video:/app/video" -v "${PWD}\app.db:/app/app.db" video-room
```

cmd:

```bash
docker build -t video-room .
docker run --rm -p 8000:8000 -v "%cd%/video:/app/video" -v "%cd%/app.db:/app/app.db" video-room
```

## Тесты

```bash
pytest
```
