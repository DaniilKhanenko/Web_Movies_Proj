# Video Room

Веб-приложение для совместного просмотра видео.

Стек:

- FastAPI
- SQLite
- обычные HTML, CSS и JavaScript
- WebSocket

React, Django и docker-compose не используются.

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
DEFENSE_REPORT.md
```

`DEFENSE_REPORT.md` - краткий отчет для подготовки к защите: ручки, базы данных, сущности и ответы на частые вопросы.

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

Откройте:

```text
http://localhost:8000
```

С телефона в той же Wi-Fi сети:

```text
http://IP_ВАШЕГО_НОУТБУКА:8000
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
pip install -e ".[test]"
pytest
```
