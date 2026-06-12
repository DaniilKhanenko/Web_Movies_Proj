async function api(path, options = {}) {
  const headers = options.headers || {};
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "Ошибка запроса");
  }

  return data;
}

async function apiJson(path, body, method = "POST") {
  return api(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function getCurrentUser() {
  try {
    return await api("/api/me");
  } catch {
    location.href = "/login";
  }
}

function setupLogout() {
  const button = document.getElementById("logout-button");
  if (!button) {
    return;
  }

  button.addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    location.href = "/login";
  });
}

function formatBytes(bytes) {
  if (!bytes) {
    return "0 MB";
  }

  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function drawPlaceholder(canvas, text) {
  const context = canvas.getContext("2d");
  context.fillStyle = "#111827";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.fillStyle = "#e5e7eb";
  context.font = "18px Arial";
  context.textAlign = "center";
  context.fillText(text || "Видео", canvas.width / 2, canvas.height / 2);
}

function makeVideoPreview(canvas, videoUrl, title) {
  drawPlaceholder(canvas, title);
  const video = document.createElement("video");
  canvas.__video = video;

  video.muted = true;
  video.preload = "metadata";
  video.playsInline = true;

  try {
    const parsed = new URL(videoUrl, location.href);
    if (parsed.origin !== location.origin) {
      video.crossOrigin = "anonymous";
    }
  } catch (e) {
  }

  let cleaned = false;
  function cleanup() {
    if (cleaned) return;
    cleaned = true;
    try { video.pause(); } catch (e) {}
    try { video.removeAttribute("src"); } catch (e) {}
    try { video.src = ""; video.load(); } catch (e) {}
    try { if (video.parentNode) video.parentNode.removeChild(video); } catch (e) {}
  }

  video.addEventListener("loadedmetadata", () => {
    const targetTime = Number.isFinite(video.duration) ? Math.min(2, video.duration / 4) : 0.2;
    try {
      video.currentTime = targetTime || 0.2;
    } catch (e) {
      video.addEventListener("canplay", function onCanplay() {
        try { video.currentTime = targetTime || 0.2; } catch (e) {}
      }, { once: true });
    }
  });

  let _suppressNextError = false;
  function _errorHandler() {
    const err = video.error || {};
    if (_suppressNextError) {
      _suppressNextError = false;
      return;
    }
    drawPlaceholder(canvas, title);
    cleanup();
  }

  video.addEventListener("error", _errorHandler);

  video.addEventListener("seeked", () => {
    try {
      const context = canvas.getContext("2d");
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
    } catch (e) {
      drawPlaceholder(canvas, title);
    }
    _suppressNextError = true;
    cleanup();
  });

  video.style.position = "absolute";
  video.style.left = "-9999px";
  video.style.width = "1px";
  video.style.height = "1px";
  document.body.appendChild(video);

  video.src = videoUrl;
  video.load();

  try {
    const p = video.play();
    if (p && p.then) {
      p.then(() => { try { video.pause(); } catch (e) {} }).catch(() => {});
    }
  } catch (e) {}
}
