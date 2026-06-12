const form = document.getElementById("auth-form");
const registerButton = document.getElementById("register-button");
const message = document.getElementById("message");

async function submitAuth(path) {
  message.textContent = "";

  try {
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    await apiJson(path, { username, password });
    location.href = "/catalog";
  } catch (error) {
    message.textContent = error.message;
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth("/api/login");
});

registerButton.addEventListener("click", () => {
  submitAuth("/api/register");
});
