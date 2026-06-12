const catalog = document.getElementById("catalog");
const message = document.getElementById("message");
const roomDialog = document.getElementById("room-dialog");
const createRoomForm = document.getElementById("create-room-form");
const roomDialogMessage = document.getElementById("room-dialog-message");

let movies = [];

setupLogout();

init();

async function init() {
  const user = await getCurrentUser();
  document.getElementById("username").textContent = user.username;

  if (user.is_admin) {
    document.getElementById("admin-link").classList.remove("hidden");
  }

  await loadMovies();
}

async function loadMovies() {
  const data = await api("/api/movies");
  movies = data.movies;
  catalog.innerHTML = "";

  if (!movies.length) {
    message.textContent = "Фильмов пока нет. Админ может загрузить их в админке.";
    return;
  }

  for (const movie of movies) {
    catalog.appendChild(createMovieCard(movie));
  }
}

function createMovieCard(movie) {
  const card = document.createElement("article");
  card.className = "movie-card";

  const canvas = document.createElement("canvas");
  canvas.width = 480;
  canvas.height = 270;
  canvas.className = "preview";
  makeVideoPreview(canvas, movie.video_url, movie.title);

  const title = document.createElement("h2");
  title.textContent = movie.title;

  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `${movie.original_name} · ${formatBytes(movie.size_bytes)}`;

  const button = document.createElement("button");
  button.textContent = "Смотреть";
  button.addEventListener("click", () => openCreateRoomDialog(movie));

  card.append(canvas, title, meta, button);
  return card;
}

function openCreateRoomDialog(movie) {
  document.getElementById("dialog-title").textContent = movie.title;
  document.getElementById("selected-movie-id").value = movie.id;
  document.getElementById("room-title").value = movie.title;
  document.getElementById("room-password").value = "";
  document.getElementById("custom-room-id").value = "";
  roomDialogMessage.textContent = "";
  message.textContent = "";
  roomDialog.showModal();
}

document.getElementById("close-dialog-button").addEventListener("click", () => {
  roomDialog.close();
});

createRoomForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  roomDialogMessage.textContent = "";

  const password = document.getElementById("room-password").value;
  if (!password.trim()) {
    roomDialogMessage.textContent = "Введите пароль комнаты.";
    document.getElementById("room-password").focus();
    return;
  }

  if (password.length < 3) {
    roomDialogMessage.textContent = "Пароль комнаты минимум 3 символа.";
    document.getElementById("room-password").focus();
    return;
  }

  try {
    const room = await apiJson("/api/rooms", {
      title: document.getElementById("room-title").value,
      password,
      room_id: document.getElementById("custom-room-id").value,
      movie_id: document.getElementById("selected-movie-id").value,
    });

    location.href = `/room/${encodeURIComponent(room.id)}`;
  } catch (error) {
    roomDialogMessage.textContent = error.message;
  }
});

document.getElementById("join-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    const roomId = document.getElementById("join-room-id").value.trim();
    const password = document.getElementById("join-room-password").value;
    await apiJson(`/api/rooms/${encodeURIComponent(roomId)}/join`, { password });
    location.href = `/room/${encodeURIComponent(roomId)}`;
  } catch (error) {
    message.textContent = error.message;
  }
});
