const uploadForm = document.getElementById("upload-form");
const movieList = document.getElementById("movie-list");
const message = document.getElementById("message");

setupLogout();
init();

async function init() {
  const user = await getCurrentUser();

  if (!user.is_admin) {
    location.href = "/catalog";
    return;
  }

  await loadMovies();
}

async function loadMovies() {
  const data = await api("/api/movies");
  movieList.innerHTML = "";

  for (const movie of data.movies) {
    const row = document.createElement("article");
    row.className = "admin-movie";

    const canvas = document.createElement("canvas");
    canvas.width = 240;
    canvas.height = 135;
    canvas.className = "admin-preview";
    makeVideoPreview(canvas, movie.video_url, movie.title);

    const text = document.createElement("div");
    text.innerHTML = `<strong>${movie.title}</strong><p class="muted">${movie.original_name} · ${formatBytes(movie.size_bytes)}</p>`;

    const deleteButton = document.createElement("button");
    deleteButton.className = "danger";
    deleteButton.textContent = "Удалить";
    deleteButton.addEventListener("click", () => deleteMovie(movie.id));

    row.append(canvas, text, deleteButton);
    movieList.appendChild(row);
  }
}


async function deleteMovie(movieId) {
  if (!confirm("Удалить фильм?")) {
    return;
  }

  document.querySelectorAll(".admin-preview").forEach(canvas => {
    if (canvas.__video) {
      canvas.__video.pause();
      canvas.__video.removeAttribute("src");
      canvas.__video.src = "";
      canvas.__video.load();
    }
  });

  movieList.innerHTML = '<p class="muted">Удаление...</p>';

  await new Promise((resolve) => setTimeout(resolve, 500));

  try {
    await api(`/api/admin/movies/${movieId}`, { method: "DELETE" });
  } catch (error) {
    alert("Ошибка: " + error.message);
  }
  
  await loadMovies();
}

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  
  message.className = "message info";
  message.textContent = "Загрузка...";

  try {
    const formData = new FormData();
    formData.append("title", document.getElementById("movie-title").value);
    formData.append("file", document.getElementById("movie-file").files[0]);

    await api("/api/admin/movies", {
      method: "POST",
      body: formData,
    });

    uploadForm.reset();
    
    message.className = "message success";
    message.textContent = "Фильм загружен";
    
    await loadMovies();
  } catch (error) {
    message.className = "message";
    message.textContent = error.message;
  }
});
