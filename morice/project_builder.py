import html
import json
import re


def _clean_title(request: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", request or "")
    stop = {
        "a",
        "an",
        "and",
        "app",
        "build",
        "create",
        "for",
        "in",
        "it",
        "make",
        "me",
        "of",
        "please",
        "site",
        "the",
        "to",
        "website",
        "with",
    }
    useful = [word for word in words if word.lower() not in stop]
    if not useful:
        return "MORICE Project"
    title = " ".join(useful[:5]).strip()
    return title[:64] or "MORICE Project"


def _is_web_like_request(request: str) -> bool:
    lowered = (request or "").lower()
    return any(
        marker in lowered
        for marker in {
            "browser",
            "css",
            "dashboard",
            "frontend",
            "game",
            "games",
            "html",
            "landing",
            "page",
            "site",
            "ui",
            "web app",
            "website",
        }
    )


def _wants_games(request: str) -> bool:
    lowered = (request or "").lower()
    return any(marker in lowered for marker in {"game", "games", "playable", "arcade"})


def _web_manifest(request: str) -> dict:
    title = _clean_title(request)
    escaped_title = html.escape(title)
    prompt_json = json.dumps(request.strip() or "Build a polished MORICE project")
    games_enabled = _wants_games(request)
    game_hint = (
        "Three mini-games are included because the request asked for playable content."
        if games_enabled
        else "The game deck is included as an interactive starter area that can be renamed or removed."
    )

    index_html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escaped_title}</title>
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <canvas id="galaxy" aria-hidden="true"></canvas>
    <div class="cursor-glow" aria-hidden="true"></div>

    <main class="shell">
      <section class="hero">
        <p class="eyebrow">MORICE Project Mode Build</p>
        <h1>{escaped_title}</h1>
        <p class="summary" id="requestSummary"></p>
        <div class="hero-actions" aria-label="Primary actions">
          <a class="button primary" href="#games">Play</a>
          <a class="button secondary" href="#features">Explore</a>
        </div>
      </section>

      <section class="feature-grid" id="features" aria-label="Project features">
        <article>
          <span>01</span>
          <h2>Reactive Galaxy</h2>
          <p>The background follows the cursor and keeps moving even when the page is idle.</p>
        </article>
        <article>
          <span>02</span>
          <h2>Dark Liquid UI</h2>
          <p>Layered glass, smooth transitions, and responsive spacing are built into the first screen.</p>
        </article>
        <article>
          <span>03</span>
          <h2>Playable Core</h2>
          <p>{html.escape(game_hint)}</p>
        </article>
      </section>

      <section class="games" id="games" aria-label="Mini games">
        <div class="section-heading">
          <p class="eyebrow">Game Deck</p>
          <h2>Three fast mini-games</h2>
        </div>

        <div class="tabs" role="tablist" aria-label="Choose a game">
          <button class="tab active" data-game="reflex" type="button">Reflex Core</button>
          <button class="tab" data-game="memory" type="button">Memory Grid</button>
          <button class="tab" data-game="catcher" type="button">Star Catcher</button>
        </div>

        <div class="game-panels">
          <section class="game-panel active" data-panel="reflex">
            <div>
              <h3>Reflex Core</h3>
              <p>Wait for the core to turn green, then strike as fast as you can.</p>
            </div>
            <button class="game-button" id="reflexButton" type="button">Start</button>
            <p class="score" id="reflexScore">Best: none</p>
          </section>

          <section class="game-panel" data-panel="memory">
            <div>
              <h3>Memory Grid</h3>
              <p>Repeat the glow sequence. Each round adds one more tile.</p>
            </div>
            <div class="memory-grid" id="memoryGrid" aria-label="Memory grid"></div>
            <button class="button secondary compact" id="memoryStart" type="button">New sequence</button>
            <p class="score" id="memoryScore">Round: 0</p>
          </section>

          <section class="game-panel" data-panel="catcher">
            <div>
              <h3>Star Catcher</h3>
              <p>Catch ten stars before the timer runs out.</p>
            </div>
            <div class="catcher-field" id="catcherField">
              <button id="starTarget" type="button" aria-label="Catch star"></button>
            </div>
            <button class="button secondary compact" id="catcherStart" type="button">Start run</button>
            <p class="score" id="catcherScore">Stars: 0 / 10</p>
          </section>
        </div>
      </section>
    </main>

    <script>
      window.MORICE_PROJECT_PROMPT = {prompt_json};
    </script>
    <script src="app.js"></script>
  </body>
</html>
"""

    styles_css = """* {
  box-sizing: border-box;
}

:root {
  color-scheme: dark;
  --bg: #04070d;
  --text: #f5f7fb;
  --muted: #aab5c8;
  --cyan: #5de4ff;
  --violet: #8f64ff;
  --green: #7cf7b5;
  --rose: #ff6d9c;
  --panel: rgba(10, 15, 28, 0.72);
  --line: rgba(180, 218, 255, 0.18);
}

html {
  scroll-behavior: smooth;
}

body {
  min-height: 100vh;
  margin: 0;
  background: radial-gradient(circle at 12% 10%, rgba(143, 100, 255, 0.16), transparent 34%),
    radial-gradient(circle at 88% 18%, rgba(93, 228, 255, 0.14), transparent 30%),
    linear-gradient(135deg, #03050a 0%, #100a1f 45%, #031a22 100%);
  color: var(--text);
  font-family: "Segoe UI", Inter, system-ui, sans-serif;
  overflow-x: hidden;
}

button,
a {
  font: inherit;
}

#galaxy {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: -2;
}

.cursor-glow {
  position: fixed;
  width: 28rem;
  height: 28rem;
  margin: -14rem 0 0 -14rem;
  border-radius: 50%;
  pointer-events: none;
  background: radial-gradient(circle, rgba(93, 228, 255, 0.2), rgba(143, 100, 255, 0.12) 38%, transparent 68%);
  mix-blend-mode: screen;
  transform: translate3d(var(--mx, 50vw), var(--my, 50vh), 0);
  transition: transform 160ms ease-out;
  z-index: -1;
}

.shell {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  padding: 56px 0 72px;
}

.hero {
  min-height: 72vh;
  display: grid;
  align-content: center;
  gap: 20px;
}

.eyebrow {
  margin: 0;
  color: var(--green);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1,
h2,
h3,
p {
  margin-top: 0;
}

h1 {
  max-width: 880px;
  margin-bottom: 0;
  font-size: clamp(2.7rem, 8vw, 7.6rem);
  line-height: 0.92;
  letter-spacing: 0;
}

h2 {
  font-size: clamp(1.8rem, 4vw, 3.6rem);
  line-height: 1;
  letter-spacing: 0;
}

h3 {
  font-size: 1.28rem;
  letter-spacing: 0;
}

.summary {
  max-width: 720px;
  color: var(--muted);
  font-size: clamp(1rem, 2vw, 1.24rem);
  line-height: 1.7;
}

.hero-actions,
.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.button,
.tab,
.game-button {
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--text);
  text-decoration: none;
  cursor: pointer;
  transition: transform 180ms ease, border-color 180ms ease, background 180ms ease, box-shadow 180ms ease;
}

.button {
  display: inline-flex;
  min-height: 44px;
  align-items: center;
  justify-content: center;
  padding: 0 18px;
}

.primary {
  background: linear-gradient(135deg, rgba(143, 100, 255, 0.94), rgba(36, 180, 210, 0.88));
  box-shadow: 0 18px 42px rgba(93, 228, 255, 0.16);
}

.secondary,
.tab {
  background: rgba(8, 12, 22, 0.72);
}

.compact {
  width: fit-content;
}

.button:hover,
.tab:hover,
.game-button:hover {
  transform: translateY(-2px);
  border-color: rgba(124, 247, 181, 0.58);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: -40px 0 72px;
}

.feature-grid article,
.game-panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.22);
  backdrop-filter: blur(18px);
}

.feature-grid article {
  min-height: 170px;
  padding: 20px;
}

.feature-grid span {
  color: var(--cyan);
  font-weight: 900;
}

.feature-grid p,
.game-panel p {
  color: var(--muted);
  line-height: 1.62;
}

.games {
  padding-top: 12px;
}

.section-heading {
  margin-bottom: 18px;
}

.tab {
  min-height: 40px;
  padding: 0 14px;
  font-weight: 800;
}

.tab.active {
  background: rgba(93, 228, 255, 0.16);
  border-color: rgba(93, 228, 255, 0.62);
}

.game-panels {
  margin-top: 14px;
}

.game-panel {
  display: none;
  min-height: 360px;
  padding: 22px;
}

.game-panel.active {
  display: grid;
  gap: 18px;
  align-content: start;
}

.game-button {
  width: min(100%, 360px);
  min-height: 90px;
  background: rgba(143, 100, 255, 0.18);
  font-size: 1.4rem;
  font-weight: 900;
}

.game-button.ready {
  background: rgba(124, 247, 181, 0.25);
  border-color: rgba(124, 247, 181, 0.72);
  box-shadow: 0 0 36px rgba(124, 247, 181, 0.22);
}

.score {
  min-height: 28px;
  margin-bottom: 0;
  color: var(--green);
  font-weight: 800;
}

.memory-grid {
  display: grid;
  width: min(100%, 340px);
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.memory-tile {
  aspect-ratio: 1;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
}

.memory-tile.flash,
.memory-tile:hover {
  transform: scale(1.04);
  background: rgba(93, 228, 255, 0.34);
  box-shadow: 0 0 28px rgba(93, 228, 255, 0.26);
}

.catcher-field {
  position: relative;
  width: min(100%, 520px);
  height: 260px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.24);
}

#starTarget {
  position: absolute;
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 50%;
  background: radial-gradient(circle, #ffffff 0 12%, var(--green) 13% 42%, transparent 43%),
    conic-gradient(from 0deg, var(--cyan), var(--violet), var(--rose), var(--green), var(--cyan));
  box-shadow: 0 0 24px rgba(124, 247, 181, 0.62);
  cursor: pointer;
}

@media (max-width: 780px) {
  .shell {
    width: min(100% - 22px, 680px);
    padding-top: 32px;
  }

  .hero {
    min-height: 68vh;
  }

  .feature-grid {
    grid-template-columns: 1fr;
    margin-top: 0;
  }
}
"""

    app_js = """const prompt = window.MORICE_PROJECT_PROMPT || "Build a polished MORICE project.";
document.getElementById("requestSummary").textContent = prompt;

const glow = document.querySelector(".cursor-glow");
window.addEventListener("pointermove", (event) => {
  document.documentElement.style.setProperty("--mx", `${event.clientX}px`);
  document.documentElement.style.setProperty("--my", `${event.clientY}px`);
  if (glow) glow.style.opacity = "1";
});

const canvas = document.getElementById("galaxy");
const ctx = canvas.getContext("2d");
let width = 0;
let height = 0;
let pointerX = 0.5;
let pointerY = 0.5;
const stars = Array.from({ length: 160 }, (_, index) => ({
  x: Math.random(),
  y: Math.random(),
  z: Math.random() * 0.8 + 0.2,
  hue: index % 3,
}));

function resizeCanvas() {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

window.addEventListener("resize", resizeCanvas);
window.addEventListener("pointermove", (event) => {
  pointerX = event.clientX / Math.max(1, width);
  pointerY = event.clientY / Math.max(1, height);
});
resizeCanvas();

function drawGalaxy(time) {
  ctx.clearRect(0, 0, width, height);
  const driftX = (pointerX - 0.5) * 34;
  const driftY = (pointerY - 0.5) * 26;
  for (const star of stars) {
    star.y += 0.00022 * star.z;
    if (star.y > 1.04) star.y = -0.04;
    const x = star.x * width + driftX * star.z + Math.sin(time * 0.0003 + star.x * 8) * 8;
    const y = star.y * height + driftY * star.z;
    const radius = 0.8 + star.z * 2.2;
    const alpha = 0.28 + star.z * 0.72;
    const colors = ["93, 228, 255", "143, 100, 255", "124, 247, 181"];
    ctx.fillStyle = `rgba(${colors[star.hue]}, ${alpha})`;
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }
  requestAnimationFrame(drawGalaxy);
}
requestAnimationFrame(drawGalaxy);

const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".game-panel");
tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const game = tab.dataset.game;
    tabs.forEach((item) => item.classList.toggle("active", item === tab));
    panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === game));
  });
});

const reflexButton = document.getElementById("reflexButton");
const reflexScore = document.getElementById("reflexScore");
let reflexStart = 0;
let reflexTimer = 0;
let reflexBest = null;

reflexButton.addEventListener("click", () => {
  if (reflexButton.classList.contains("ready")) {
    const score = performance.now() - reflexStart;
    reflexBest = reflexBest === null ? score : Math.min(reflexBest, score);
    reflexButton.classList.remove("ready");
    reflexButton.textContent = "Start";
    reflexScore.textContent = `Last: ${Math.round(score)} ms | Best: ${Math.round(reflexBest)} ms`;
    return;
  }
  window.clearTimeout(reflexTimer);
  reflexButton.textContent = "Wait...";
  reflexScore.textContent = "Do not click until the core turns green.";
  reflexTimer = window.setTimeout(() => {
    reflexStart = performance.now();
    reflexButton.classList.add("ready");
    reflexButton.textContent = "Strike";
  }, 850 + Math.random() * 1800);
});

const grid = document.getElementById("memoryGrid");
const memoryStart = document.getElementById("memoryStart");
const memoryScore = document.getElementById("memoryScore");
const tiles = Array.from({ length: 16 }, (_, index) => {
  const tile = document.createElement("button");
  tile.className = "memory-tile";
  tile.type = "button";
  tile.dataset.index = String(index);
  tile.setAttribute("aria-label", `Memory tile ${index + 1}`);
  grid.appendChild(tile);
  return tile;
});
let sequence = [];
let inputIndex = 0;
let acceptingMemory = false;

function flashTile(index) {
  const tile = tiles[index];
  tile.classList.add("flash");
  window.setTimeout(() => tile.classList.remove("flash"), 280);
}

async function playSequence() {
  acceptingMemory = false;
  for (const index of sequence) {
    flashTile(index);
    await new Promise((resolve) => window.setTimeout(resolve, 430));
  }
  inputIndex = 0;
  acceptingMemory = true;
}

function nextMemoryRound() {
  sequence.push(Math.floor(Math.random() * tiles.length));
  memoryScore.textContent = `Round: ${sequence.length}`;
  playSequence();
}

memoryStart.addEventListener("click", () => {
  sequence = [];
  nextMemoryRound();
});

tiles.forEach((tile) => {
  tile.addEventListener("click", () => {
    if (!acceptingMemory) return;
    const value = Number(tile.dataset.index);
    flashTile(value);
    if (value !== sequence[inputIndex]) {
      acceptingMemory = false;
      memoryScore.textContent = `Missed at round ${sequence.length}. Start again.`;
      return;
    }
    inputIndex += 1;
    if (inputIndex >= sequence.length) {
      acceptingMemory = false;
      window.setTimeout(nextMemoryRound, 520);
    }
  });
});

const catcherField = document.getElementById("catcherField");
const starTarget = document.getElementById("starTarget");
const catcherStart = document.getElementById("catcherStart");
const catcherScore = document.getElementById("catcherScore");
let starsCaught = 0;
let catcherActive = false;
let catcherDeadline = 0;

function moveStar() {
  const bounds = catcherField.getBoundingClientRect();
  const x = Math.random() * Math.max(1, bounds.width - 48);
  const y = Math.random() * Math.max(1, bounds.height - 48);
  starTarget.style.transform = `translate(${x}px, ${y}px)`;
}

function updateCatcherScore() {
  const remaining = Math.max(0, Math.ceil((catcherDeadline - performance.now()) / 1000));
  catcherScore.textContent = `Stars: ${starsCaught} / 10 | Time: ${remaining}s`;
  if (!catcherActive) return;
  if (starsCaught >= 10) {
    catcherActive = false;
    catcherScore.textContent = "Run complete. Perfect catch.";
    return;
  }
  if (remaining <= 0) {
    catcherActive = false;
    catcherScore.textContent = `Time out. Stars caught: ${starsCaught} / 10`;
    return;
  }
  window.requestAnimationFrame(updateCatcherScore);
}

catcherStart.addEventListener("click", () => {
  starsCaught = 0;
  catcherActive = true;
  catcherDeadline = performance.now() + 20000;
  moveStar();
  updateCatcherScore();
});

starTarget.addEventListener("click", () => {
  if (!catcherActive) return;
  starsCaught += 1;
  moveStar();
});

moveStar();
"""

    readme = f"""# {title}

Built by MORICE Project mode from this request:

```text
{request.strip() or "No request text captured."}
```

## Files

- `index.html` is the app shell.
- `styles.css` contains the dark liquid-galaxy visual system.
- `app.js` powers the cursor-reactive background and mini-games.

## Run

Open `index.html` in a browser, or serve the folder with:

```powershell
python -m http.server 5173
```

Then open `http://localhost:5173`.
"""

    return {
        "summary": f"Built a polished static web project for {title}.",
        "files": [
            {"path": "index.html", "content": index_html},
            {"path": "styles.css", "content": styles_css},
            {"path": "app.js", "content": app_js},
            {"path": "README.md", "content": readme},
        ],
        "commands": ["python -m http.server 5173"],
        "notes": [
            "This fallback runs without npm or external assets.",
            "The generated files can be edited by later Project mode prompts.",
        ],
    }


def _python_tool_manifest(request: str) -> dict:
    title = _clean_title(request)
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", title.lower()).strip("_") or "morice_tool"
    prompt_json = json.dumps(request.strip() or "Build a useful Python tool")
    main_py = f'''"""
{title}

Generated by MORICE Project mode as a safe local Python starter.
"""

from __future__ import annotations

import argparse
from pathlib import Path


PROJECT_REQUEST = {prompt_json}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="{safe_name}", description=PROJECT_REQUEST)
    parser.add_argument("--input", type=Path, help="Optional input file to read.")
    parser.add_argument("--output", type=Path, help="Optional output file to write.")
    return parser


def run(input_path: Path | None = None) -> str:
    if input_path and input_path.exists():
        content = input_path.read_text(encoding="utf-8", errors="replace")
        return f"Loaded {{len(content)}} characters from {{input_path}}."
    return "Starter is ready. Add the project-specific logic in run()."


def main() -> int:
    args = build_parser().parse_args()
    result = run(args.input)
    if args.output:
        args.output.write_text(result + "\\n", encoding="utf-8")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''
    readme = f"""# {title}

Built by MORICE Project mode from this request:

```text
{request.strip() or "No request text captured."}
```

## Run

```powershell
python main.py
```

This is a safe starter when the local model does not return a complete file manifest. Ask MORICE for a follow-up edit to add the exact behavior you want.
"""
    return {
        "summary": f"Built a Python starter project for {title}.",
        "files": [
            {"path": "main.py", "content": main_py},
            {"path": "README.md", "content": readme},
        ],
        "commands": ["python main.py"],
        "notes": ["Ask for a follow-up Project edit to expand this starter into the exact tool behavior."],
    }


def build_project_fallback_manifest(request: str) -> dict | None:
    text = " ".join((request or "").split())
    if not text:
        return None
    lowered = text.lower()
    if _is_web_like_request(text):
        return _web_manifest(text)
    if any(marker in lowered for marker in {"python", "script", "cli", "automation", "tool"}):
        return _python_tool_manifest(text)
    return _web_manifest(text)
