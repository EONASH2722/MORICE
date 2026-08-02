from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


LANGUAGE_RULES = (
    ("C++", (r"(?<!\w)c\+\+(?!\w)", r"\bcpp\b"), (".cpp", ".cc", ".cxx", ".hpp", ".h")),
    ("C#", (r"(?<!\w)c#(?!\w)", r"\bcsharp\b", r"\.net\b"), (".cs", ".csproj")),
    ("TypeScript", (r"\btypescript\b", r"\btsx\b"), (".ts", ".tsx")),
    ("JavaScript", (r"\bjavascript\b", r"\bjs\b", r"\bnode(?:\.js)?\b"), (".js", ".mjs", ".cjs")),
    ("Python", (r"\bpython\b", r"\bpygame\b", r"\bpy\b"), (".py",)),
    ("Rust", (r"\brust\b", r"\bcargo\b"), (".rs", ".toml")),
    ("Go", (r"\bgolang\b", r"\bgo language\b", r"\bgo app\b", r"\b(?:in|using|with)\s+go\b"), (".go",)),
    ("Java", (r"\bjava\b",), (".java", ".gradle", ".xml")),
    ("Kotlin", (r"\bkotlin\b",), (".kt", ".kts", ".gradle")),
    ("Swift", (r"\bswift\b", r"\bswiftui\b"), (".swift",)),
    ("Dart", (r"\bdart\b", r"\bflutter\b"), (".dart", ".yaml")),
    ("PHP", (r"\bphp\b",), (".php",)),
    ("Ruby", (r"\bruby\b", r"\brails\b"), (".rb",)),
    ("Lua", (r"\blua\b", r"\blove2d\b"), (".lua",)),
    ("Scala", (r"\bscala\b",), (".scala", ".sbt")),
    ("Haskell", (r"\bhaskell\b",), (".hs", ".cabal")),
    ("Elixir", (r"\belixir\b", r"\bphoenix\b"), (".ex", ".exs")),
    ("Erlang", (r"\berlang\b",), (".erl", ".hrl")),
    ("Julia", (r"\bjulia\b",), (".jl",)),
    ("R", (r"\br language\b", r"\brscript\b", r"\b(?:in|using|with)\s+r\b"), (".r",)),
    ("Zig", (r"\bzig\b",), (".zig",)),
    ("Nim", (r"\bnim\b",), (".nim",)),
    ("OCaml", (r"\bocaml\b",), (".ml", ".mli", ".dune")),
    ("F#", (r"(?<!\w)f#(?!\w)", r"\bfsharp\b"), (".fs", ".fsx", ".fsproj")),
    ("Visual Basic", (r"\bvisual basic\b", r"\bvb\.net\b"), (".vb", ".vbproj")),
    ("PowerShell", (r"\bpowershell\b",), (".ps1", ".psm1")),
    ("Bash", (r"\bbash\b", r"\bshell script\b"), (".sh",)),
    ("GDScript", (r"\bgdscript\b",), (".gd", ".tscn", ".tres")),
    ("Solidity", (r"\bsolidity\b",), (".sol",)),
    ("Fortran", (r"\bfortran\b",), (".f", ".f90", ".f95")),
    ("COBOL", (r"\bcobol\b",), (".cob", ".cbl")),
    ("Perl", (r"\bperl\b",), (".pl", ".pm")),
    ("C", (r"\bc language\b", r"\bansi c\b"), (".c", ".h")),
    ("HTML/CSS/JavaScript", (r"\bhtml\b", r"\bcss\b", r"\bvanilla js\b"), (".html", ".css", ".js")),
)

FRAMEWORK_RULES = (
    ("React Native", (r"\breact[\s-]+native\b",)),
    ("Babylon.js", (r"\bbabylon(?:\.js|js)\b",)),
    ("Three.js", (r"\bthree(?:\.js|js)\b",)),
    ("Next.js", (r"\bnext(?:\.js|js)\b",)),
    ("FastAPI", (r"\bfastapi\b",)),
    ("JavaFX", (r"\bjavafx\b",)),
    ("Love2D", (r"\blove2d\b",)),
    ("SwiftUI", (r"\bswiftui\b",)),
    ("OpenGL", (r"\bopengl\b",)),
    ("Raylib", (r"\braylib\b",)),
    ("Django", (r"\bdjango\b",)),
    ("Electron", (r"\belectron\b",)),
    ("Flutter", (r"\bflutter\b",)),
    ("Godot", (r"\bgodot\b",)),
    ("Laravel", (r"\blaravel\b",)),
    ("Phaser", (r"\bphaser\b",)),
    ("Pygame", (r"\bpygame\b",)),
    ("React", (r"\breact(?:\.js|js)?\b",)),
    ("Svelte", (r"\bsvelte\b",)),
    ("Unity", (r"\bunity\b",)),
    ("Unreal", (r"\bunreal(?:\s+engine)?\b",)),
    ("Vue", (r"\bvue(?:\.js|js)?\b",)),
    ("Bevy", (r"\bbevy\b",)),
    ("Qt", (r"\bqt(?:5|6)?\b",)),
)

FOLLOW_UP_MARKERS = (
    "add ",
    "also ",
    "change ",
    "continue ",
    "edit ",
    "fix ",
    "improve ",
    "in it",
    "make it",
    "now ",
    "polish ",
    "replace ",
    "update ",
)

TITLE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "app",
    "application",
    "build",
    "code",
    "create",
    "for",
    "fully",
    "game",
    "generate",
    "in",
    "it",
    "make",
    "me",
    "of",
    "please",
    "polished",
    "project",
    "responsive",
    "site",
    "the",
    "to",
    "using",
    "website",
    "with",
}


class ProjectIntentError(ValueError):
    """Raised when generated files do not implement the user's stated request."""


@dataclass(frozen=True)
class ProjectRequestSpec:
    request: str
    kind: str
    subject: str
    language: str
    extensions: tuple[str, ...]
    framework: str
    dimension: str
    follow_up: bool

    @property
    def title(self) -> str:
        if self.subject == "flappy bird":
            return "Flappy Bird 3D" if self.dimension == "3d" else "Flappy Bird"
        words = re.findall(r"[A-Za-z0-9+#.-]+", self.request)
        useful = [word for word in words if word.casefold() not in TITLE_STOP_WORDS]
        return (" ".join(useful[:6]).strip() or "MORICE Project")[:64]


def analyze_project_request(request: str, has_existing_project: bool = False) -> ProjectRequestSpec:
    clean = " ".join((request or "").split())
    lowered = clean.casefold()

    language = ""
    extensions: tuple[str, ...] = ()
    for candidate, patterns, candidate_extensions in LANGUAGE_RULES:
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns):
            language = candidate
            extensions = candidate_extensions
            break

    framework = next(
        (
            name
            for name, patterns in FRAMEWORK_RULES
            if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)
        ),
        "",
    )
    if not language:
        if framework in {"Three.js", "Babylon.js", "Phaser", "React", "Vue", "Svelte", "Next.js", "Electron"}:
            language, extensions = "JavaScript", (".js", ".mjs", ".cjs")
        elif framework == "Pygame":
            language, extensions = "Python", (".py",)
        elif framework == "Unity":
            language, extensions = "C#", (".cs", ".csproj")
        elif framework == "Godot":
            language, extensions = "GDScript", (".gd", ".tscn", ".tres")

    subject = ""
    if re.search(r"\bflap+y\s+bird\b|\bflappybird\b", lowered):
        subject = "flappy bird"
    elif "snake" in lowered:
        subject = "snake"
    elif re.search(r"\btic[\s-]*tac[\s-]*toe\b", lowered):
        subject = "tic tac toe"
    elif "pong" in lowered:
        subject = "pong"

    if any(word in lowered for word in ("game", "playable", "arcade")) or subject:
        kind = "game"
    elif any(word in lowered for word in ("api", "backend", "server", "endpoint")):
        kind = "api"
    elif any(word in lowered for word in ("website", "web app", "landing page", "dashboard", "frontend", "site")):
        kind = "web"
    elif any(word in lowered for word in ("cli", "command line", "script", "automation", "tool")):
        kind = "tool"
    elif any(word in lowered for word in ("mobile app", "desktop app", "application", " app")):
        kind = "app"
    else:
        kind = "project"

    if kind == "game" and not subject:
        game_match = re.search(r"(.{1,96}?)\s+(?:video\s+)?game\b", lowered)
        if game_match:
            subject_words = [
                word
                for word in re.findall(r"[a-z0-9+#.-]+", game_match.group(1))
                if word not in TITLE_STOP_WORDS
                and word not in {"2d", "3d", "original", "simple", "small", "full", "working", "browser"}
            ]
            subject = " ".join(subject_words[-4:])

    dimension = "3d" if re.search(r"\b3[\s-]*d\b|three[\s-]*dimensional", lowered) else (
        "2d" if re.search(r"\b2[\s-]*d\b|two[\s-]*dimensional", lowered) else ""
    )
    follow_up = has_existing_project and any(marker in lowered for marker in FOLLOW_UP_MARKERS)
    return ProjectRequestSpec(clean, kind, subject, language, extensions, framework, dimension, follow_up)


def project_request_contract(request: str, has_existing_project: bool = False) -> str:
    spec = analyze_project_request(request, has_existing_project)
    lines = [
        "PROJECT ACCEPTANCE CONTRACT",
        f"- Deliverable: {spec.kind}",
        f"- Requested subject: {spec.subject or 'infer the central product from the full request'}",
        f"- Language: {spec.language or 'choose the most suitable language only because the user did not name one'}",
        f"- Framework: {spec.framework or 'choose only when it materially helps'}",
        f"- Dimension: {spec.dimension or 'not explicitly specified'}",
        f"- Existing-project edit: {'yes' if spec.follow_up else 'no'}",
        "- Implement the requested behavior itself. The prompt must not merely become a heading, description, or TODO.",
        "- Do not substitute another game, app, or feature that the user did not request.",
        "- Include startup, input, core behavior, success/failure state, restart/recovery, and responsive layout where relevant.",
        "- Preserve unrelated existing behavior on follow-up edits.",
    ]
    if spec.kind == "game":
        lines.extend(
            [
                "- The result must be playable, with a real update loop, input handling, collision/rules, score or progress, and restart.",
                "- Menu copy or a static mockup does not count as a game.",
            ]
        )
    if spec.subject == "flappy bird":
        lines.append(
            "- Flappy Bird requires flap input, gravity/vertical velocity, moving pipe gaps, collision, score, game over, and restart."
        )
    if spec.dimension == "3d":
        lines.append(
            "- 3D must use a real 3D renderer or a genuine perspective scene with depth geometry; a flat heading saying 3D is insufficient."
        )
    return "\n".join(lines)


def _manifest_files(manifest: dict) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in (manifest.get("files") or [])[:80]:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/").strip()
        content = item.get("content")
        if path and isinstance(content, str):
            result.append((path, content))
    return result


def validate_project_manifest_intent(manifest: dict, request: str) -> None:
    spec = analyze_project_request(request)
    files = _manifest_files(manifest)
    if not files:
        raise ProjectIntentError("The model did not return practical source files.")

    paths = [path.casefold() for path, _content in files]
    combined = "\n".join(f"{path}\n{content}" for path, content in files).casefold()
    code_chars = sum(
        len(content)
        for path, content in files
        if Path(path).suffix.casefold() not in {".md", ".txt"}
    )

    if spec.language and spec.extensions:
        if not any(Path(path).suffix.casefold() in spec.extensions for path in paths):
            expected = ", ".join(spec.extensions)
            raise ProjectIntentError(
                f"The generated project ignored the requested {spec.language} language (expected {expected})."
            )

    framework_token = spec.framework.casefold().replace(".js", "")
    if spec.framework and framework_token not in combined.replace(".js", ""):
        framework_evidence = {
            "Unity": ("monobehaviour", "unityengine"),
            "Godot": ("extends node", "extends characterbody", ".tscn"),
            "Pygame": ("pygame.init", "pygame.display"),
            "Three.js": ("three.module", "webglrenderer", "new three."),
            "OpenGL": ("glfw", "glad", "glbegin", "glcreate"),
            "Raylib": ("initwindow", "begindrawing", "raylib.h"),
        }.get(spec.framework, ())
        if not framework_evidence or not any(term in combined for term in framework_evidence):
            raise ProjectIntentError(f"The generated project did not use the requested {spec.framework} framework.")

    if spec.kind == "game":
        if code_chars < 1_200:
            raise ProjectIntentError("The generated game is only a stub or static page.")
        mechanics = (
            "requestanimationframe",
            "gameloop",
            "game loop",
            "collision",
            "score",
            "velocity",
            "update(",
            "_process(",
            "tick(",
        )
        if sum(term in combined for term in mechanics) < 2:
            raise ProjectIntentError("The generated files do not contain a playable game loop and mechanics.")
        if spec.subject and spec.subject not in {"flappy bird", "snake", "tic tac toe", "pong"}:
            subject_terms = [term for term in spec.subject.split() if len(term) >= 4]
            implementation_text = "\n".join(
                content.casefold()
                for path, content in files
                if Path(path).suffix.casefold() not in {".html", ".md", ".txt"}
            )
            if subject_terms and not any(
                term in implementation_text or combined.count(term) >= 2
                for term in subject_terms
            ):
                raise ProjectIntentError(
                    f"The generated game does not implement the requested {spec.subject} subject."
                )

    subject_mechanics = {
        "flappy bird": (
            ("flappy", "bird"),
            ("pipe", "obstacle"),
            ("gravity", "velocity"),
            ("flap", "jump"),
            ("score",),
            ("collision", "intersect", "hit"),
            ("restart", "resetgame", "reset_game"),
        ),
        "snake": (
            ("snake",),
            ("food", "apple"),
            ("direction", "velocity"),
            ("body", "segments", "tail"),
            ("collision", "gameover", "game_over"),
            ("score",),
            ("restart", "resetgame", "reset_game"),
        ),
        "pong": (
            ("pong",),
            ("paddle",),
            ("ball",),
            ("collision", "bounce"),
            ("score",),
            ("restart", "resetgame", "reset_game"),
        ),
        "tic tac toe": (
            ("tic", "tac", "toe"),
            ("board", "cells"),
            ("winner", "winpatterns", "winning"),
            ("turn", "currentplayer", "current_player"),
            ("restart", "resetgame", "reset_game"),
        ),
    }
    required_groups = subject_mechanics.get(spec.subject)
    if required_groups:
        missing = ["/".join(group) for group in required_groups if not any(term in combined for term in group)]
        if missing:
            raise ProjectIntentError(
                f"The generated files do not implement {spec.subject.title()} mechanics: missing "
                + ", ".join(missing)
                + "."
            )

    if spec.dimension == "3d":
        depth_evidence = (
            "webgl",
            "perspective:",
            "perspective(",
            "preserve-3d",
            "translatez",
            "three.",
            "babylon.",
            "opengl",
            "directx",
            "unityengine",
            "camera3d",
            "meshinstance3d",
        )
        if not any(term in combined for term in depth_evidence):
            raise ProjectIntentError("The generated project claimed 3D without implementing a 3D scene.")


def _web_manifest(request: str) -> dict:
    spec = analyze_project_request(request)
    title = spec.title
    escaped_title = html.escape(title)
    escaped_request = html.escape(request)
    index_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header class="topbar"><strong>{escaped_title}</strong><button id="themeButton" type="button">Theme</button></header>
  <main>
    <section class="hero">
      <p class="eyebrow">Built with MORICE</p>
      <h1>{escaped_title}</h1>
      <p>{escaped_request}</p>
      <button id="primaryAction" type="button">Get started</button>
    </section>
    <section class="workspace" id="workspace" aria-live="polite">
      <h2>Ready</h2>
      <p>The project shell is running. Continue in Project Mode to add domain-specific data and integrations.</p>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
"""
    styles_css = """* { box-sizing: border-box; }
:root { color-scheme: dark; --bg:#090b11; --panel:#141923; --text:#f5f7fb; --muted:#a9b2c3; --accent:#62d6a8; }
:root.light { color-scheme: light; --bg:#f4f6fa; --panel:#fff; --text:#151922; --muted:#566174; --accent:#087f5b; }
body { min-height:100vh; margin:0; background:var(--bg); color:var(--text); font:16px/1.6 "Segoe UI",sans-serif; }
button { min-height:42px; border:1px solid color-mix(in srgb,var(--accent) 55%,transparent); border-radius:6px; padding:0 16px; background:var(--accent); color:#04120d; font-weight:700; cursor:pointer; }
.topbar { height:60px; display:flex; align-items:center; justify-content:space-between; padding:0 max(20px,5vw); border-bottom:1px solid #ffffff18; }
main { width:min(1040px,calc(100% - 32px)); margin:auto; }
.hero { min-height:62vh; display:grid; align-content:center; justify-items:start; gap:14px; }
.eyebrow { color:var(--accent); font-weight:800; }
h1 { max-width:850px; margin:0; font-size:clamp(2.6rem,8vw,6.4rem); line-height:1; letter-spacing:0; }
.hero p { max-width:720px; color:var(--muted); }
.workspace { margin-bottom:64px; padding:24px; border:1px solid #ffffff1c; border-radius:8px; background:var(--panel); }
"""
    app_js = """const root = document.documentElement;
const workspace = document.getElementById("workspace");
document.getElementById("themeButton").addEventListener("click", () => root.classList.toggle("light"));
document.getElementById("primaryAction").addEventListener("click", () => {
  workspace.scrollIntoView({ behavior: "smooth" });
  workspace.querySelector("h2").textContent = "Project active";
});
"""
    readme = f"""# {title}

MORICE created this dependency-free browser project from:

```text
{request}
```

Open `index.html`, or run `python -m http.server 5173`.
"""
    return {
        "summary": f"Built a focused browser project for {title}.",
        "files": [
            {"path": "index.html", "content": index_html},
            {"path": "styles.css", "content": styles_css},
            {"path": "app.js", "content": app_js},
            {"path": "README.md", "content": readme},
        ],
        "commands": ["python -m http.server 5173"],
        "notes": ["This emergency fallback creates one focused project and never substitutes unrelated mini-games."],
    }


FLAPPY_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Flappy Bird 3D</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="game-shell">
    <header class="hud">
      <strong>FLAPPY BIRD 3D</strong>
      <div><span>Score <b id="score">0</b></span><span>Best <b id="best">0</b></span></div>
    </header>
    <section class="viewport" id="viewport" aria-label="Flappy Bird 3D game">
      <div class="sky sky-far"></div><div class="sky sky-near"></div>
      <div class="world" id="world">
        <div class="bird" id="bird"><i></i><i></i><i></i><i></i><i></i><i></i><span class="wing"></span></div>
        <div id="pipes"></div>
        <div class="ground"></div>
      </div>
      <section class="overlay" id="overlay">
        <p class="eyebrow">A real playable Project Mode build</p>
        <h1 id="overlayTitle">Flappy Bird 3D</h1>
        <p id="overlayText">Fly through the pipe gaps. Press Space, click, or tap to flap.</p>
        <button id="startButton" type="button">Start game</button>
      </section>
    </section>
    <footer><span>Space / click / tap: flap</span><button id="pauseButton" type="button">Pause</button></footer>
  </main>
  <script src="game.js"></script>
</body>
</html>
"""

FLAPPY_STYLES = """* { box-sizing:border-box; }
:root { color-scheme:dark; --ink:#f7fbff; --cyan:#48d7ff; --green:#63e87b; --deep:#050a12; }
html,body { width:100%; min-height:100%; margin:0; overflow:hidden; background:var(--deep); color:var(--ink); font-family:"Segoe UI",sans-serif; }
button { font:inherit; }
.game-shell { width:100vw; height:100vh; display:grid; grid-template-rows:64px 1fr 48px; background:#07111f; }
.hud,footer { z-index:20; display:flex; align-items:center; justify-content:space-between; padding:0 clamp(16px,4vw,48px); background:#07101be8; border-color:#ffffff18; }
.hud { border-bottom:1px solid #ffffff18; }
.hud>div { display:flex; gap:22px; }
.hud span,footer { color:#b6c4d6; }
.hud b { margin-left:6px; color:var(--cyan); font-size:1.25rem; }
.viewport { position:relative; min-height:0; overflow:hidden; perspective:900px; isolation:isolate; touch-action:manipulation; }
.sky { position:absolute; inset:-10%; background-repeat:repeat-x; pointer-events:none; }
.sky-far { background:linear-gradient(#09254b 0 55%,#17658b 75%,#70d4d0 100%); }
.sky-near { opacity:.55; background:radial-gradient(circle at 15% 25%,#fff 0 2px,transparent 3px),radial-gradient(circle at 70% 18%,#bdeaff 0 1px,transparent 2px); background-size:180px 120px,130px 100px; }
.world { position:absolute; inset:0; transform-style:preserve-3d; transform:rotateX(-2deg) rotateY(-6deg) translateZ(-30px) scale(1.03); transform-origin:center; }
.ground { position:absolute; left:-10%; right:-10%; bottom:-9%; height:20%; transform:rotateX(66deg) translateZ(-70px); background:repeating-linear-gradient(90deg,#397544 0 44px,#2e663b 45px 88px); border-top:8px solid #92ee78; box-shadow:0 -10px 45px #3cff7b33; }
.bird { position:absolute; width:54px; height:40px; left:24%; top:45%; z-index:8; transform-style:preserve-3d; transform:translate3d(0,0,70px) rotateZ(var(--tilt,0deg)); filter:drop-shadow(0 8px 8px #0008); }
.bird i { position:absolute; inset:0; background:#ffd84d; border:3px solid #492d19; }
.bird i:nth-child(1){transform:translateZ(14px)} .bird i:nth-child(2){transform:rotateY(180deg) translateZ(14px)}
.bird i:nth-child(3){width:28px;transform:rotateY(90deg) translateZ(40px);transform-origin:right}
.bird i:nth-child(4){width:28px;transform:rotateY(-90deg) translateZ(14px);transform-origin:left}
.bird i:nth-child(5){height:28px;transform:rotateX(90deg) translateZ(14px);transform-origin:top}
.bird i:nth-child(6){height:28px;transform:rotateX(-90deg) translateZ(12px);transform-origin:bottom}
.bird:before { content:""; position:absolute; z-index:4; width:19px; height:13px; right:-17px; top:14px; background:#ff794c; clip-path:polygon(0 0,100% 50%,0 100%); transform:translateZ(18px); }
.bird:after { content:""; position:absolute; z-index:5; width:9px; height:9px; right:8px; top:7px; border-radius:50%; background:#10151b; border:3px solid white; transform:translateZ(17px); }
.wing { position:absolute; z-index:6; width:34px; height:18px; left:4px; top:17px; border:3px solid #492d19; border-radius:70% 20% 70% 20%; background:#ff9e45; transform-origin:right center; transform:translateZ(18px) rotate(var(--wing,0deg)); }
.pipe { position:absolute; top:0; width:92px; height:100%; transform-style:preserve-3d; will-change:transform; }
.pipe-part { position:absolute; left:0; width:76px; margin-left:8px; border:4px solid #173f22; background:linear-gradient(90deg,#2c8d43,#86ef74 45%,#2b793a); box-shadow:inset -12px 0 #1b5b2d,0 10px 20px #0005; transform:translateZ(22px); }
.pipe-part:before { content:""; position:absolute; left:-12px; right:-12px; height:30px; background:linear-gradient(90deg,#2d7b3c,#9cff83 46%,#215c31); border:4px solid #173f22; }
.pipe-part:after { content:""; position:absolute; top:0; right:-24px; width:24px; height:100%; background:#215d30; transform-origin:left; transform:rotateY(90deg); }
.pipe-top { top:0; } .pipe-top:before { bottom:-4px; } .pipe-bottom { bottom:0; } .pipe-bottom:before { top:-4px; }
.overlay { position:absolute; z-index:30; left:50%; top:50%; width:min(520px,calc(100% - 32px)); padding:28px; transform:translate(-50%,-50%); border:1px solid #ffffff28; border-radius:8px; background:#07101bee; box-shadow:0 30px 90px #000b; text-align:center; backdrop-filter:blur(16px); }
.overlay[hidden] { display:none; }
.overlay h1 { margin:6px 0 12px; font-size:clamp(2rem,7vw,4.2rem); line-height:1; }
.overlay p { color:#bdc9d8; }
.eyebrow { color:#76ef9c!important; font-weight:800; }
button { min-height:42px; padding:0 18px; border:1px solid #ffffff2d; border-radius:6px; color:white; background:#225bdb; font-weight:800; cursor:pointer; }
button:hover { filter:brightness(1.12); }
footer { border-top:1px solid #ffffff18; font-size:.9rem; }
footer button { min-height:34px; background:#162235; }
@media(max-width:650px){.hud{height:56px}.game-shell{grid-template-rows:56px 1fr 44px}.bird{left:20%;transform:scale(.82) translate3d(0,0,70px) rotateZ(var(--tilt,0deg))}.pipe{width:72px}.pipe-part{width:60px}.hud>strong{font-size:.9rem}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
"""

FLAPPY_GAME = """(() => {
  "use strict";
  const viewport = document.getElementById("viewport");
  const bird = document.getElementById("bird");
  const pipesLayer = document.getElementById("pipes");
  const scoreLabel = document.getElementById("score");
  const bestLabel = document.getElementById("best");
  const overlay = document.getElementById("overlay");
  const overlayTitle = document.getElementById("overlayTitle");
  const overlayText = document.getElementById("overlayText");
  const startButton = document.getElementById("startButton");
  const pauseButton = document.getElementById("pauseButton");
  const state = { running:false, paused:false, birdY:0, velocity:0, score:0, best:Number(localStorage.getItem("flappy3d-best")||0), pipes:[], last:0, spawn:0 };
  bestLabel.textContent = String(state.best);

  function metrics(){ const rect=viewport.getBoundingClientRect(); return { width:rect.width, height:rect.height, birdX:rect.width*.24, birdW:54, birdH:40, ground:rect.height*.91 }; }
  function resetGame(){
    const m=metrics(); state.birdY=m.height*.43; state.velocity=0; state.score=0; state.spawn=0; state.pipes.forEach(pipe=>pipe.node.remove()); state.pipes=[]; scoreLabel.textContent="0"; renderBird();
  }
  function makePipe(){
    const m=metrics(); const gap=Math.max(138,Math.min(210,m.height*.29)); const margin=Math.max(76,m.height*.12); const gapY=margin+Math.random()*Math.max(1,m.ground-gap-margin*2);
    const node=document.createElement("div"); node.className="pipe"; node.innerHTML='<div class="pipe-part pipe-top"></div><div class="pipe-part pipe-bottom"></div>';
    node.querySelector(".pipe-top").style.height=`${Math.max(20,gapY-gap/2)}px`; node.querySelector(".pipe-bottom").style.height=`${Math.max(20,m.height-(gapY+gap/2))}px`; pipesLayer.appendChild(node);
    state.pipes.push({ node, x:m.width+100, gapTop:gapY-gap/2, gapBottom:gapY+gap/2, scored:false });
  }
  function flap(){ if(!state.running){ startGame(); return; } if(state.paused)return; state.velocity=-Math.max(390,metrics().height*.58); bird.style.setProperty("--wing","-35deg"); setTimeout(()=>bird.style.setProperty("--wing","18deg"),100); }
  function collision(pipe,m){ const pad=7; const birdLeft=m.birdX+pad, birdRight=m.birdX+m.birdW-pad, birdTop=state.birdY+pad, birdBottom=state.birdY+m.birdH-pad; return birdRight>pipe.x+8&&birdLeft<pipe.x+84&&(birdTop<pipe.gapTop||birdBottom>pipe.gapBottom); }
  function renderBird(){ const tilt=Math.max(-24,Math.min(72,state.velocity*.075)); bird.style.top=`${state.birdY}px`; bird.style.setProperty("--tilt",`${tilt}deg`); }
  function finish(){ state.running=false; state.best=Math.max(state.best,state.score); localStorage.setItem("flappy3d-best",String(state.best)); bestLabel.textContent=String(state.best); overlayTitle.textContent="Game over"; overlayText.textContent=`Score ${state.score}. Press Space, click, or tap to fly again.`; startButton.textContent="Restart"; overlay.hidden=false; }
  function update(dt){
    const m=metrics(); state.velocity+=Math.max(1050,m.height*1.5)*dt; state.birdY+=state.velocity*dt; state.spawn-=dt; if(state.spawn<=0){makePipe();state.spawn=Math.max(1.25,1.75-state.score*.015)}
    const speed=Math.max(190,m.width*.24); for(const pipe of state.pipes){pipe.x-=speed*dt;pipe.node.style.transform=`translate3d(${pipe.x}px,0,${Math.max(-80,80-(m.width-pipe.x)*.12)}px)`;if(!pipe.scored&&pipe.x+84<m.birdX){pipe.scored=true;state.score+=1;scoreLabel.textContent=String(state.score)}if(collision(pipe,m)){finish();return}}
    state.pipes=state.pipes.filter(pipe=>{if(pipe.x<-120){pipe.node.remove();return false}return true}); if(state.birdY<0||state.birdY+m.birdH>m.ground){finish();return} renderBird();
  }
  function frame(now){ const dt=Math.min(.034,(now-state.last)/1000||0);state.last=now;if(state.running&&!state.paused)update(dt);requestAnimationFrame(frame)}
  function startGame(){resetGame();state.running=true;state.paused=false;pauseButton.textContent="Pause";overlay.hidden=true;state.last=performance.now();flap()}
  function togglePause(){if(!state.running)return;state.paused=!state.paused;pauseButton.textContent=state.paused?"Resume":"Pause"}
  startButton.addEventListener("click",startGame); pauseButton.addEventListener("click",togglePause); viewport.addEventListener("pointerdown",event=>{if(event.target.closest("button"))return;flap()}); window.addEventListener("keydown",event=>{if(event.code==="Space"){event.preventDefault();flap()}if(event.code==="KeyP")togglePause()}); window.addEventListener("resize",()=>{if(!state.running)resetGame()});
  resetGame(); requestAnimationFrame(frame);
})();
"""


def _flappy_bird_manifest(request: str, project_root: str | None = None) -> dict:
    existing_index = Path(project_root, "index.html") if project_root else None
    integrate = bool(existing_index and existing_index.is_file())
    prefix = "flappy-bird-3d/" if integrate else ""
    files = [
        {"path": prefix + "index.html", "content": FLAPPY_INDEX},
        {"path": prefix + "styles.css", "content": FLAPPY_STYLES},
        {"path": prefix + "game.js", "content": FLAPPY_GAME},
        {
            "path": prefix + "README.md",
            "content": "# Flappy Bird 3D\n\nPlayable CSS-3D browser game with gravity, pipes, collisions, scoring, pause, game over, and restart.\n",
        },
    ]
    if integrate and existing_index:
        current = existing_index.read_text(encoding="utf-8", errors="replace")
        marker = "data-morice-flappy-bird"
        if marker not in current:
            launcher = (
                '\n<a data-morice-flappy-bird href="flappy-bird-3d/index.html" '
                'style="position:fixed;right:18px;bottom:18px;z-index:9999;padding:12px 16px;'
                'border-radius:6px;background:#225bdb;color:white;text-decoration:none;font:700 14px Segoe UI,sans-serif">'
                "Play Flappy Bird 3D</a>\n"
            )
            current, replaced = re.subn(
                r"</body\s*>",
                launcher + "</body>",
                current,
                count=1,
                flags=re.IGNORECASE,
            )
            if not replaced:
                current += launcher
            files.append({"path": "index.html", "content": current})
    return {
        "summary": "Built a real playable Flappy Bird 3D game.",
        "files": files,
        "commands": ["Open " + prefix + "index.html in a browser"],
        "notes": [
            "Uses dependency-free CSS 3D geometry and a real-time game loop.",
            "Includes flap input, gravity, moving pipe gaps, collision, score, best score, pause, game over, and restart.",
        ],
    }


def build_project_fallback_manifest(request: str, project_root: str | None = None) -> dict | None:
    text = " ".join((request or "").split())
    if not text:
        return None
    spec = analyze_project_request(text, bool(project_root and os.path.isdir(project_root)))
    if spec.subject == "flappy bird":
        return _flappy_bird_manifest(text, project_root)
    if spec.kind == "game":
        # Returning the old generic mini-game page was worse than failing:
        # it silently replaced the requested game with unrelated content.
        return None
    if spec.kind == "web" or (
        not spec.language
        and any(marker in text.casefold() for marker in ("browser", "css", "frontend", "html", "page", "site"))
    ):
        return _web_manifest(text)
    return None
