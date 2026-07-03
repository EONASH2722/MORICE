const messagesEl = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const statusEl = document.querySelector("#status");
const statusText = document.querySelector("#statusText");

const messages = [
  {
    role: "assistant",
    content: "Morice is awake, All Father. Ask me something and I will keep the circuits polite and useful.",
  },
];

let busy = false;

function setStatus(text, mode = "ready") {
  statusText.textContent = text;
  statusEl.classList.toggle("busy", mode === "busy");
  statusEl.classList.toggle("error", mode === "error");
}

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function linkifyUrls(value) {
  return value.replace(/https?:\/\/[^\s<]+/g, (url) => {
    const cleanUrl = url.replace(/[),.;!?]+$/, "");
    const punctuation = url.slice(cleanUrl.length);
    return `<a href="${cleanUrl}" target="_blank" rel="noreferrer noopener">${cleanUrl}</a>${punctuation}`;
  });
}

function formatInline(value) {
  return value
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n][\s\S]*?[^*\n])\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n][\s\S]*?[^_\n])__/g, "<strong>$1</strong>");
}

function formatMessage(value) {
  return linkifyUrls(formatInline(escapeHtml(value)))
    .split(/\n{2,}/)
    .map((paragraph) => {
      const lines = paragraph.split("\n");
      const formattedLines = lines.map((line) => {
        const heading = line.match(/^#{1,6}\s+(.+)$/);
        if (heading) return `<strong>${heading[1]}</strong>`;
        const bullet = line.match(/^[-*]\s+(.+)$/);
        if (bullet) return `&bull; ${bullet[1]}`;
        return line;
      });
      return `<p>${formattedLines.join("<br>")}</p>`;
    })
    .join("");
}

function addMessage(role, content, options = {}) {
  const bubble = document.createElement("article");
  bubble.className = `message ${role}${options.queued ? " queued" : ""}`;
  bubble.innerHTML = formatMessage(content);
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

function addTyping() {
  const bubble = document.createElement("article");
  bubble.className = "message assistant thinking-bubble";
  let visible = true;
  bubble.innerHTML = `
    <button class="thinking-toggle" type="button" aria-expanded="true">
      <span class="typing" aria-label="Morice is thinking"><span></span><span></span><span></span></span>
      <span class="thinking-label">Processing</span>
    </button>
    <div class="thinking-details">
      <p id="thinkingDetail">1. Morice is preparing a reply.</p>
    </div>
  `;
  const toggle = bubble.querySelector(".thinking-toggle");
  const details = bubble.querySelector(".thinking-details");
  toggle.addEventListener("click", () => {
    visible = !visible;
    details.hidden = !visible;
    toggle.setAttribute("aria-expanded", String(visible));
  });
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

function setThinkingDetail(bubble, text) {
  const detail = bubble.querySelector("#thinkingDetail");
  if (!detail || !text) return;
  const nextLine = `${detail.textContent ? "\n" : ""}${detail.textContent.split("\n").length + 1}. ${text}`;
  detail.textContent += nextLine;
}

function renderInitialMessages() {
  messagesEl.innerHTML = "";
  for (const message of messages) {
    addMessage(message.role, message.content);
  }
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

function syncSendState() {
  const hasText = input.value.trim().length > 0;
  input.disabled = busy;
  sendButton.disabled = busy || !hasText;
  sendButton.textContent = busy ? "Wait" : "Send";
}

async function sendMessage(text) {
  if (!text || busy) return;

  busy = true;
  setStatus(/^(?:@web|\/web|web:|search:)\s+/i.test(text.trim()) ? "Searching" : "Thinking", "busy");
  syncSendState();

  messages.push({ role: "user", content: text });
  addMessage("user", text);
  const typingBubble = addTyping();
  setThinkingDetail(
    typingBubble,
    /^(?:@web|\/web|web:|search:)\s+/i.test(text.trim())
      ? "Searching the web, reading results, then asking the Hermes engine."
      : "Asking the local Hermes engine for a clean reply."
  );

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Morice could not answer.");
    }

    const reply = data.reply || "I drew a blank there. Very dramatic, not very useful.";
    messages.push({ role: "assistant", content: reply });
    typingBubble.remove();
    addMessage("assistant", reply);
    setStatus("Ready");
  } catch (error) {
    typingBubble.remove();
    const message = error.message || "Something went wrong.";
    addMessage("system", message);
    setStatus("Needs attention", "error");
  } finally {
    busy = false;
    syncSendState();
  }
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy) return;

  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  resizeInput();
  sendMessage(text);
});

input.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey) return;
  event.preventDefault();
  if (busy) return;

  composer.requestSubmit();
});

input.addEventListener("input", () => {
  resizeInput();
  syncSendState();
});

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error("Health check failed.");
    setStatus(data.ollamaOnline ? "Ready" : "Ready soon", data.ollamaOnline ? "ready" : "busy");
  } catch {
    setStatus("Needs attention", "error");
  }
}

renderInitialMessages();
resizeInput();
syncSendState();
checkHealth();
