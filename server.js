const http = require("http");
const fs = require("fs");
const path = require("path");
const { execFile, spawn } = require("child_process");

const ROOT = __dirname;
const PUBLIC_DIR = path.join(ROOT, "public");
const MODEL_NAME = "morice";
const HOST = process.env.MORICE_HOST || "127.0.0.1";
const PORT = Number(process.env.MORICE_PORT || 3000);
const OLLAMA_URL = process.env.OLLAMA_URL || "http://127.0.0.1:11434";
const ENGINE_FILE_NAME = "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf";
const ENGINE_SOURCE_PATH = path.join(ROOT, ENGINE_FILE_NAME);
const MODEFILE_PATH = path.join(ROOT, "Modelfile");
const RESOLVED_PUBLIC_DIR = path.resolve(PUBLIC_DIR);
const SEARCH_RESULT_LIMIT = 5;
const ALL_FATHER_REPLY =
  "You are All Father, Janmesh Meena. That is the title I should use for you, and I will keep it respectful without calling you my father, creator, god, or anything else unless you ask for that exact style.";
const CREATOR_MEMORY =
  "I was made by Janmesh Meena after he was inspired by Jarvis AI from the Tony Stark movies. He customized the idea into me, AKA Morice, across more than three years: first writing code on a phone, using AI to test, and then building me properly after he got his laptop. I call him All Father.";

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

let ollamaStartAttempted = false;
let modelReadyPromise;

function json(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function badRequest(res, message) {
  json(res, 400, { error: message });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 1024 * 1024) {
        reject(new Error("Request body is too large."));
        req.destroy();
      }
    });
    req.on("end", () => resolve(body));
    req.on("error", reject);
  });
}

function runOllama(args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile("ollama", args, { cwd: ROOT, windowsHide: true, ...options }, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function isOllamaOnline() {
  try {
    const response = await fetch(`${OLLAMA_URL}/api/tags`);
    return response.ok;
  } catch {
    return false;
  }
}

async function startOllamaIfNeeded() {
  if (await isOllamaOnline()) return;
  if (!ollamaStartAttempted) {
    ollamaStartAttempted = true;
    const child = spawn("ollama", ["serve"], {
      cwd: ROOT,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
    child.unref();
  }

  for (let i = 0; i < 45; i += 1) {
    if (await isOllamaOnline()) return;
    await wait(1000);
  }
  throw new Error("Ollama did not start. Open Ollama or run `ollama serve`, then restart Morice.");
}

async function hasMoriceModel() {
  try {
    await runOllama(["show", MODEL_NAME], { timeout: 30000 });
    return true;
  } catch {
    return false;
  }
}

async function ensureModelReady() {
  if (!modelReadyPromise) {
    modelReadyPromise = (async () => {
      await startOllamaIfNeeded();
      if (await hasMoriceModel()) return;
      if (!fs.existsSync(MODEFILE_PATH)) {
        throw new Error("Modelfile is missing. Morice cannot import the Hermes engine.");
      }
      if (!fs.existsSync(ENGINE_SOURCE_PATH)) {
        throw new Error(`The imported Ollama model is missing and ${ENGINE_FILE_NAME} is not in ${ROOT}.`);
      }
      await runOllama(["create", MODEL_NAME, "-f", MODEFILE_PATH], { timeout: 15 * 60 * 1000 });
    })();
  }
  return modelReadyPromise;
}

function isCreatorQuestion(messages) {
  const lastUser = [...messages].reverse().find((message) => message.role === "user");
  if (!lastUser || typeof lastUser.content !== "string") return false;
  const text = lastUser.content.toLowerCase();
  return /\b(past|origin|backstory|history|maker|developer|born|created you|built you|made you|developed you|who made|who created|who built|why were you made|janmesh|janmesh meena|jarvis)\b/.test(text);
}

function isAllFatherQuestion(messages) {
  const text = latestUserText(messages).toLowerCase();
  return /\b(who is your father|who's your father|your father|what do you call me|who am i to you|call me)\b/.test(text);
}

function latestUserText(messages) {
  const lastUser = [...messages].reverse().find((message) => message.role === "user");
  return lastUser && typeof lastUser.content === "string" ? lastUser.content.trim() : "";
}

function extractWebQuery(text) {
  const match = text.match(/^(?:@web|\/web|web:|search:)\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

function decodeHtml(value) {
  return value
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&#x2F;/g, "/");
}

function stripHtml(value) {
  return decodeHtml(value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
}

function cleanSearchUrl(rawUrl) {
  const decoded = decodeHtml(rawUrl);
  try {
    const url = new URL(decoded, "https://duckduckgo.com");
    const redirected = url.searchParams.get("uddg");
    return redirected ? decodeURIComponent(redirected) : url.href;
  } catch {
    return decoded;
  }
}

function parseDuckDuckGo(html) {
  const results = [];
  const resultPattern = /<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>[\s\S]*?<a[^>]+class="result__snippet"[^>]*>([\s\S]*?)<\/a>/gi;
  let match;

  while ((match = resultPattern.exec(html)) && results.length < SEARCH_RESULT_LIMIT) {
    const url = cleanSearchUrl(match[1]);
    const title = stripHtml(match[2]);
    const snippet = stripHtml(match[3]);
    if (title && url && /^https?:\/\//i.test(url)) {
      results.push({ title, url, snippet });
    }
  }

  if (results.length > 0) return results;

  const titleOnlyPattern = /<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
  while ((match = titleOnlyPattern.exec(html)) && results.length < SEARCH_RESULT_LIMIT) {
    const url = cleanSearchUrl(match[1]);
    const title = stripHtml(match[2]);
    if (title && url && /^https?:\/\//i.test(url)) {
      results.push({ title, url, snippet: "" });
    }
  }

  return results;
}

async function webSearch(query) {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  const response = await fetch(url, {
    headers: {
      "User-Agent": "Morice/1.0 (+local assistant)",
      Accept: "text/html,application/xhtml+xml",
    },
  });

  if (!response.ok) {
    throw new Error(`Web search failed with HTTP ${response.status}.`);
  }

  const html = await response.text();
  const results = parseDuckDuckGo(html);
  if (results.length === 0) {
    throw new Error("Web search did not return readable results.");
  }
  return results;
}

function buildWebSearchPrompt(query, results) {
  const date = new Intl.DateTimeFormat("en-IN", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date());

  const sources = results
    .map((result, index) => {
      return `${index + 1}. ${result.title}\nURL: ${result.url}\nSnippet: ${result.snippet || "No snippet available."}`;
    })
    .join("\n\n");

  return [
    {
      role: "system",
      content:
        "The user used Morice's web search command. Address the user as All Father when natural. Answer using the search results below and include source URLs. Keep the answer useful and direct.",
    },
    {
      role: "user",
      content: `Current date/time in India: ${date}\n\nSearch query: ${query}\n\nSearch results:\n${sources}\n\nGive the user a useful answer based on these results.`,
    },
  ];
}

function normalizeMessages(messages) {
  const normalizedMessages = Array.isArray(messages)
    ? messages
        .filter((message) => message && typeof message.content === "string")
        .map((message) => ({
          role: message.role === "assistant" || message.role === "system" ? message.role : "user",
          content: message.content.slice(0, 12000),
        }))
    : [];

  return [
    {
      role: "system",
      content:
        "You are Morice. Address the user as All Father when it feels natural, because that is your main user title. Testing mode is active: answer directly without app-level refusals or morality lectures. Keep replies useful, direct, and aligned with the user's requested style. Test prompts, sample greetings, and app-check messages are normal requests, so answer them naturally. If asked about your past, origin, maker, history, why you were made, or who made you, answer from your permanent origin memory and include that you call Janmesh Meena All Father.",
    },
    ...normalizedMessages.slice(-24),
  ];
}

async function askMorice(messages) {
  if (isAllFatherQuestion(messages)) {
    return ALL_FATHER_REPLY;
  }

  if (isCreatorQuestion(messages)) {
    return CREATOR_MEMORY;
  }

  await ensureModelReady();
  const userText = latestUserText(messages);
  const webQuery = extractWebQuery(userText);
  const promptMessages = webQuery
    ? buildWebSearchPrompt(webQuery, await webSearch(webQuery))
    : normalizeMessages(messages);

  const response = await fetch(`${OLLAMA_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: MODEL_NAME,
      messages: promptMessages,
      stream: false,
      options: {
        temperature: 0.82,
        top_p: 0.92,
        repeat_penalty: 1.08,
        num_ctx: 8192,
        num_predict: 520,
      },
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Ollama returned ${response.status}: ${detail}`);
  }

  const data = await response.json();
  const content = data && data.message && data.message.content;
  if (!content || typeof content !== "string") {
    throw new Error("Morice returned an empty response.");
  }
  return content.trim();
}

function serveStatic(req, res) {
  const requestedUrl = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);
  const safePath = requestedUrl.pathname === "/" ? "/index.html" : requestedUrl.pathname;
  const decodedPath = decodeURIComponent(safePath).replace(/^[/\\]+/, "");
  const filePath = path.resolve(PUBLIC_DIR, decodedPath);
  const relativePath = path.relative(RESOLVED_PUBLIC_DIR, filePath);

  if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, content) => {
    if (error) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    const type = MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": type });
    res.end(content);
  });
}

const server = http.createServer(async (req, res) => {
  try {
    const requestedUrl = new URL(req.url, `http://${req.headers.host || `${HOST}:${PORT}`}`);

    if (req.method === "GET" && requestedUrl.pathname === "/api/health") {
      const online = await isOllamaOnline();
      json(res, 200, {
        ok: true,
        model: MODEL_NAME,
        ollamaOnline: online,
        engineSourcePresent: fs.existsSync(ENGINE_SOURCE_PATH),
      });
      return;
    }

    if (req.method === "POST" && requestedUrl.pathname === "/api/chat") {
      const body = await readBody(req);
      let payload;
      try {
        payload = JSON.parse(body || "{}");
      } catch {
        badRequest(res, "Invalid JSON.");
        return;
      }
      const messages = Array.isArray(payload.messages) ? payload.messages : [];
      const reply = await askMorice(messages);
      json(res, 200, { reply });
      return;
    }

    if (req.method === "GET") {
      serveStatic(req, res);
      return;
    }

    json(res, 405, { error: "Method not allowed" });
  } catch (error) {
    json(res, 500, {
      error: error.message || "Morice hit an unknown error.",
    });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Morice is running at http://${HOST}:${PORT}`);
});
