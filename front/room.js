const roomId = decodeURIComponent(location.pathname.split("/").pop());
const joinPanel = document.getElementById("join-panel");
const playerPanel = document.getElementById("player-panel");
const player = document.getElementById("video-player");
const message = document.getElementById("message");
const statusBadge = document.getElementById("connection-status");

let socket = null;
let clientId = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
let ignorePlayerEvent = false;

setupLogout();
init();

async function init() {
  await getCurrentUser();
  await loadRoom();
}

async function loadRoom() {
  try {
    const room = await api(`/api/rooms/${encodeURIComponent(roomId)}`);
    showPlayer(room);
  } catch (error) {
    joinPanel.classList.remove("hidden");
    playerPanel.classList.add("hidden");
  }
}

function showPlayer(room) {
  joinPanel.classList.add("hidden");
  playerPanel.classList.remove("hidden");
  document.getElementById("room-title").textContent = room.title;
  document.getElementById("room-id").textContent = `ID комнаты: ${room.id}`;
  player.src = room.video_url;
  player.load();
  connectSocket(room.id);
}

function connectSocket(id) {
  if (socket) {
    socket.close();
  }

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws/rooms/${id}`);

  socket.onopen = () => {
    statusBadge.textContent = "online";
    statusBadge.classList.add("online");
  };

  socket.onclose = () => {
    statusBadge.textContent = "offline";
    statusBadge.classList.remove("online");
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === "room_state") {
      applyState(data.state, true);
    }

    if (data.type === "player_event" && data.clientId !== clientId) {
      applyState(data, false);
    }
  };
}

function applyState(state, initialState) {
  ignorePlayerEvent = true;

  const position = Number(state.position || 0);
  if (Math.abs(player.currentTime - position) > 0.5) {
    player.currentTime = position;
  }
  
  player.playbackRate = state.rate || 1.0; 

  if (state.playing) {
    player.play().catch(() => {});
  } else if (!initialState) {
    player.pause();
  }

  setTimeout(() => {
    ignorePlayerEvent = false;
  }, 400);
}

function sendPlayerEvent(action) {
  if (ignorePlayerEvent || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  socket.send(
    JSON.stringify({
      type: "player_event",
      action,
      position: player.currentTime,
      playing: !player.paused,
      rate: player.playbackRate,
      clientId,
    })
  );
}

document.getElementById("room-join-form").addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    const password = document.getElementById("room-password").value;
    const room = await apiJson(`/api/rooms/${encodeURIComponent(roomId)}/join`, { password });
    showPlayer(room);
  } catch (error) {
    message.textContent = error.message;
  }
});

player.addEventListener("play", () => sendPlayerEvent("play"));
player.addEventListener("pause", () => sendPlayerEvent("pause"));
player.addEventListener("seeked", () => sendPlayerEvent("seek"));
player.addEventListener("ratechange", () => sendPlayerEvent("ratechange"));
player.addEventListener("error", () => {
  message.textContent = "Видео не воспроизводится. Проверьте формат MP4/H.264.";
});
