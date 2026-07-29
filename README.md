<p align="center">
  <img src="morice/assets/morice-logo-rgb.png" alt="MORICE logo" width="150">
</p>

# MORICE

MORICE is a local desktop AI platform for people who want an assistant that can talk, research, understand local documents, build files, operate approved desktop tools, render mathematics, and run deterministic science visualizations without losing the feel of a personal tool. It combines a PySide6 glass interface, offline GGUF/Ollama model support, trusted model browsing, semantic local search, a searchable knowledge graph, structured memory, notes lookup, optional web lookup, wake control, queued follow-up messages, an autonomous Project Mode workspace, the validated VNext rendering engine, a permission-controlled desktop environment, a process-isolated Plugin SDK, verified updates, encrypted backup, and production release tooling.

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license">
  <img src="https://img.shields.io/badge/python-3.12+-3776ab" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/UI-PySide6-41cd52" alt="PySide6">
  <img src="https://img.shields.io/badge/offline-GGUF-purple" alt="Offline GGUF">
  <img src="https://img.shields.io/badge/base%20AI-Qwen2.5%20Coder%207B-0f766e" alt="Qwen2.5 Coder 7B">
  <img src="https://img.shields.io/badge/mode-Project%20Builder-111827" alt="Project Builder">
  <img src="https://img.shields.io/badge/VNext-Science%20Workspace-0891b2" alt="Science Workspace">
  <img src="https://img.shields.io/badge/agent-typed%20tools-2563eb" alt="Typed agent tools">
  <img src="https://img.shields.io/badge/desktop-Phase%204-0ea5e9" alt="Phase 4 premium experience">
  <img src="https://img.shields.io/badge/plugins-SDK%201.0-14b8a6" alt="Plugin SDK 1.0">
  <img src="https://img.shields.io/badge/platform-Phase%207-22c55e" alt="Phase 7 autonomous platform">
  <img src="https://img.shields.io/badge/wake-adaptive%20audio-22c55e" alt="Adaptive wake audio">
</p>

<p align="center">
  <img src="docs/screenshots/morice-2026-queue.png" alt="MORICE message queue panel" width="52%">
</p>

## Workflow Map

The main MORICE modes all pass through the same intent layer, then branch into the right context source before the local model replies or applies files.

<p align="center">
  <img src="docs/morice-workflow-chain.svg" alt="MORICE Project mode, web lookup, notes lookup, and model browser workflow chain" width="100%">
</p>

## VNext Rendering Engine

MORICE renders supported visual requests directly inside Normal Chat. Background workers prepare typed artifacts, validators check the result, and the loading card is replaced by a real interactive workspace. The optional `Lab` dock archives generated artifacts; it is not required to view them.

Current VNext desktop runtime:

- Function graphs: multiple equations, piecewise, polar, parametric, implicit, roots, intercepts, extrema, and inflection points.
- Surface graphs: validated `z=f(x,y)` data with linked 2D height-map and 3D mesh views.
- Physics: particles, projectile, pendulum, spring, wave, circular motion, and orbital scenes with real simulation state.
- Chemistry: curated VSEPR molecular structures with 2D/3D views, reference angles, rotation, and atom inspection.
- Biology: validated DNA, neuron, and cell models with real geometry, labels, animation controls, and shared 2D/3D views.
- Computer science: Binary Search Trees, AVL Trees, graphs, linked lists, queues, stacks, and hash tables with live Insert/Delete/Search operations, animated highlights, and complexity reporting.
- Numeric charts: bar, pie, line, scatter, and histogram views built directly from values supplied in the prompt, with exact-value inspection and PNG/SVG/PDF export.
- Component schematics: labeled 2D/3D views for supported robots, drones, vehicles, aircraft, ships, buildings, bridges, engines, CPUs, GPUs, motherboards, cameras, and watches.
- Structured diagrams: networking, operating systems, databases, AI, security, biology, circuits, geography, economics, compiler, process-state, timelines, and explicit user-supplied flow pipelines.
- Local document previews: real in-chat text, source, JSON, CSV, image, and PDF views when the prompt contains a valid local path.
- Rich answers: local Markdown, highlighted code, tables, and KaTeX equations.
- Model-agnostic instruction shape: `simulationType`, `equations`, and `parameters`.
- Renderer registry, capability detection, bounded scheduler, artifact cache, resource cleanup, and honest failure states.
- Reusable in-chat generation card with real analysis, selection, preparation, validation, and rendering stages.
- Graph, surface, molecule, and diagram export to PNG/SVG/PDF; physics export to PNG/JSON.
- 2D/3D selectors reuse one validated dataset or physical state instead of regenerating model output.
- Pause, resume, step, step back, reset, time scale, vectors, trails, inspectors, and live statistics where applicable.
- Lab workspace dock with `Graphs`, `Simulations`, and `Notebook` tabs.
- Model-output guard that removes fake claims such as `[A graph is shown]` when no renderer validated an artifact.
- Fail-closed behavior for unsupported renderers: no fake graph, screenshot, window, or simulation description.

See `docs/vnext-science-workspace.md` for the architecture, accuracy contract, capability limits, and extension rules. The strict TypeScript engine in `vnext/` includes the coordinator, renderer manager, Plotly adapter, cache, and deterministic 2D/3D particle-state core.

## Highlights

- Premium desktop experience with Light, Dark, Midnight, Glass, and Custom themes; configurable accent/opacity; high contrast; large text; 80-160% scaling; reduced motion; searchable settings; and importable experience profiles.
- Native-style window controls, monitor-safe geometry restoration, edge snapping, fullscreen/maximized restoration, live model/GPU/RAM/VRAM/task status, and Balanced, Focus, Science, Project, and Research splitter layouts.
- Independent left/right glass message bubbles with rich Markdown/math/code rendering, timestamps, copy, edit, reactions, progressive history virtualization, and an adaptive multiline composer with attachments, voice status, model/project selection, prompt history, and quick actions.
- Local-first model routing through a bundled GGUF, a selected GGUF file, or an installed Ollama model.
- Trusted model browser with automatic GPU/VRAM detection, one-click trusted model lanes, compatibility scoring, worth scoring, official-source links, licenses, task metadata, and model-speciality summaries.
- Project Mode with a readable right-side Files/Changes/Output workspace, project tree, source preview, green/red patch review, source validation, run actions, and a cancellable allowlisted terminal.
- Project prompts become validated patch previews. `Apply patch` grants permission for that exact change set, `Reject` leaves the folder untouched, and `Undo` restores the previous file state.
- VNext inline workspaces for real graphs, surfaces, physics, molecules, biology, data structures, numeric charts, component schematics, structured diagrams, local documents, and rich mathematics directly in Normal Chat.
- `@web` lookup for fresh information when needed, with results passed into the local reply pipeline instead of leaving the whole chat online by default.
- `@notes` lookup for local knowledge files, so MORICE can answer from personal documents without uploading them.
- Adaptive wake listener that can launch MORICE by saved phrase or double clap, amplify quiet speech, learn persistent room noise, recover split phrases, and rotate away from silent or incompatible microphones.
- Message queue for follow-up steering while a long local reply is still generating.
- Personalization and appearance panel for the user title, wake phrase, response style, emoji amount, maturity level, five themes, accessibility/motion controls, workspace presets, and built-in or user-added fonts. Expressive emoji mode actively shapes replies, while MORICE's voice combines human cadence with precise machine reasoning.
- Typo-aware and short-form-aware intent handling, so rough wording can still land in the right workflow.
- Verified capability answers: questions such as `what all rendering can you do` return a complete implemented-feature inventory instead of an improvised model reply.
- Process-isolated Plugin SDK with typed manifests, mandatory permission review, dependency/version checks, lifecycle state tracking, hot reload, crash recovery, native tool/renderer/command contributions, a searchable local/HTTPS marketplace, checksum-verified packages, version pinning, rollback, diagnostics, and developer templates.
- Unified Phase 7 orchestrator with specialist coding, research, planning, documentation, debugging, testing, visualization, simulation, desktop, file, and voice responsibilities; structured messages; project progress; recovery; and one shared platform snapshot.
- Searchable local SQLite knowledge graph for projects, notes, research, conversations, documents, code relationships, plugins, preferences, visualizations, and simulations with project-aware relevance and secret redaction.
- Project dashboard for architecture, dependencies, Git state, commits, timeline, issues, open files, memory, renderers, builds, tests, and performance.
- Exact-approval Git creation, clone, branch, merge, commit, tag, revert, conflict resolution, and local releases plus read-only diff, history, conflicts, and visual timeline data.
- Windows DPAPI secure settings and encrypted backups, bounded export bundles, stable/beta update channels, SHA-256 verified staging, restart-time portable/installer updates, rollback copies, first-run hardware guidance, repair checks, and release-readiness diagnostics.
- Hardened release lifecycle: only ZIP/EXE update packages are accepted, installer completion is checked before success is recorded, portable rollback generations cannot collide, shutdown continues every cleanup step after a component failure, and the CLI exposes working `--help` and `--version` commands.
- MIT licensed, so the project can be studied, forked, customized, and improved.

## Autonomous Platform

Phase 7 connects the existing agent, Project Mode, desktop environment, VNext,
plugins, memory, recovery, and diagnostics layers. Models still do not execute
actions directly. The application owns permissions, tools, writes, renderers,
verification, progress, and recovery.

Open `Tools` and select `Platform` to inspect the current project, autonomous
runs, local knowledge graph, update channel, and release readiness. Project
work is represented as a resumable workflow from plan and diff preview through
approved apply, build, tests, debugging, documentation, and memory update.

Destructive stages, Git mutations, and update installation require exact,
expiring, one-use approval. Git commits are path-scoped, rollback uses `revert`
rather than destructive reset, backups and exports reject traversal and secret
files, and Windows secret storage has no plaintext fallback.

The packaged first launch detects GPU, VRAM, RAM, and storage, recommends a
local model class, explains permissions, and creates the first workspace.
`installer/MORICE.iss` produces a per-user Windows installer;
`scripts/build-release.ps1` runs tests, builds PyInstaller, creates optional
portable/installer artifacts, and emits SHA-256 checksums.
Because the offline installer includes the local model, its Setup executable
and numbered data slices must remain together. The portable Zip64 release is
the single-file distribution option.

See [`docs/phase-7-autonomous-platform.md`](docs/phase-7-autonomous-platform.md),
[`docs/user-manual.md`](docs/user-manual.md), and
[`docs/troubleshooting.md`](docs/troubleshooting.md) for architecture,
workflows, security boundaries, operation, and recovery.

## Plugin SDK

Open **Plugin Center** from `Ctrl+K` to install, inspect, pause, reload, update,
or remove extensions. Plugin Center also includes version-specific permission
review, runtime diagnostics, local/HTTPS marketplace catalogs, and a developer
workspace that generates and packages sample plugins.

Plugins run in separate bounded processes. MORICE validates their manifest,
dependencies, platform compatibility, and requested permissions before code
runs. A plugin crash or timeout removes its active tools and renderers without
taking down the desktop app. Plugin packages reject traversal paths, symlinks,
oversized payloads, and core-file writes.

Supported contribution families include models, tools, deterministic renderers,
commands, themes, workspaces, settings, memory providers, voice providers, and
automations. The public lifecycle/event/API contract and complete sample are in
[`docs/plugin-sdk.md`](docs/plugin-sdk.md).

```powershell
python -m morice.plugin_cli init .\hello-plugin --id example.hello --name "Hello MORICE"
python -m morice.plugin_cli validate .\hello-plugin
python -m morice.plugin_cli pack .\hello-plugin --output .\hello-plugin.zip
```

## Agent Runtime

Every request enters a typed agent pipeline before MORICE replies:

```text
intent -> context -> memory -> project index -> capability -> plan
       -> tool selection -> permission -> execution -> verification
       -> renderer -> UI -> final response
```

The application executes actions; the model only reasons and prepares
structured output. MORICE does not treat model prose as proof that a file,
command, Git action, or renderer succeeded.

- Multi-intent routing splits coding, search, terminal, science, document, and
  conversation work into explicit subtasks.
- The project index records bounded file metadata, languages, frameworks,
  dependencies, symbols, imports, build systems, entry points, assets, recent
  Git state, and request-relevant source context.
- Typed tools publish schemas, permissions, platform support, dependencies,
  timeout, cancellation, version, health, risk, and idempotency metadata.
- Tool inputs and outputs are validated. Results contain real duration,
  output, warnings, errors, files, artifacts, logs, screenshots, metadata, and
  verification status.
- Permission tokens are one-use and bound to the exact tool plus arguments.
  A token cannot be reused for a different patch or command.
- File patches are previewed before approval, written atomically, checked
  after writing, and backed by a verified undo record.
- Read-only actions can be replayed. Mutation actions are never replayed
  automatically.
- Terminal execution uses argument arrays rather than shell expansion,
  captures stdout/stderr and exit status, supports timeout and cancellation,
  and records the action.
- Git status, diff, branches, history, and blame are read-only tools. Stash,
  restore, checkout, commit, and push require exact explicit approval.
- Model routing records task profile, latency, estimated throughput, context
  usage, failures, fallback candidates, temperature, and GPU-layer metadata.
- Context budgeting keeps current instructions and relevant recent/project
  context while compressing older turns before overflow.
- Renderer requests cannot pass verification unless a real renderer validator
  confirms the artifact. Missing output is a failure, not a prose success.
- Patch history redacts file bodies, stale previews are refused, failed
  multi-file writes roll back, and undo protects edits made after MORICE's
  patch.

See [`docs/phase-2-agent-architecture.md`](docs/phase-2-agent-architecture.md)
for contracts, extension rules, verification behavior, and current limits.

## Diagnostics, Health, and Recovery

MORICE now has one runtime-services layer for application health instead of
scattered background work and session-only status messages. Open
`/diagnostics`, use the System tab, or choose **Advanced diagnostics** from the
desktop tools to inspect:

- startup checks for storage, assets, dependencies, settings, model, GPU,
  desktop tools, and renderer plugins;
- searchable rotating JSONL logs with timestamps, levels, categories, thread
  names, and structured metadata;
- CPU, memory, frame-time, FPS, task-queue, renderer-cache, and worker metrics;
- application, Python, Qt, operating-system, model, GPU, renderer, and tool
  versions or capability states;
- an `Agent` tab with the active pipeline stages, routed intents, model health,
  registered typed tools, and recent verified or refused actions;
- bounded crash recovery for recent chat history, drafts, and queued messages.

Critical startup failures are shown explicitly instead of allowing a partially
initialized desktop session. Owned model processes and managed worker threads
are stopped during normal shutdown. See
[`docs/phase-1-foundation-audit.md`](docs/phase-1-foundation-audit.md) for the
architecture audit, verification contract, and remaining modularity work.

## Desktop Workspace

MORICE now includes a persistent, resizable `Tools` dock, `Ctrl+K` command palette, and a modular Phase 3 desktop integration layer. This layer is separate from VNext: it organizes conversations and verified local-computer actions while the existing inline renderer continues to own graphs and simulations.

- `Dashboard`: recent chats, recent files, and focused quick actions.
- `Files`: semantic bounded search plus safe text, code, JSON, XML, CSV, image, PDF, audio/video, Office-text, and archive previews; downloads have their own sub-tab.
- `Search Everywhere`: one query spans local files, registered projects, structured memory, commands, typed tools, and runtime logs.
- `Activity`: timeline, queued tasks, live local logs, and an opt-in in-memory clipboard history that is never written to the session file.
- `Tools`: CPU/GPU/RAM/storage/network/battery status, persistent local notes, an embedded browser when Qt WebEngine is available, local audio/video playback, and Windows media controls.
- `Desktop managers`: independent permission, application, window, file, document, multimodal, clipboard, notification, media, monitor, screenshot, automation, voice, workspace, memory, and session services.
- `Applications and windows`: real Windows discovery/process enumeration, launch/close/restart, focus/minimize/maximize/restore, move/resize, layouts, and recent/pinned application state.
- `Files and documents`: recent/large-file collections, SHA-256 duplicate detection, project discovery, metadata, tags, bookmarks, bounded multi-file context, extracted Office text, tables, formulas, entities, and source-line citations.
- `Screenshots`: validated full-screen, window, region, delayed, clipboard, and optional annotated PNG capture through an approval-gated backend.
- `Automations`: disabled-by-default registered workflows with conditions, variables, delays, bounded repeats, daily/interval schedules, and no arbitrary code evaluation.
- `Memory`: bounded conversation/session/project/user/temporary/archive records with relevant retrieval, inspect, search, pin, archive, delete, import, export, and a master disable.
- Appearance: dark and light themes with outlined sun/moon title-bar controls, a user-selectable accent, built-in font choices, validated local TTF/OTF/TTC fonts, three emoji levels, three maturity levels, stable glass panels, compact native-style window controls, and motion that respects `MORICE_REDUCE_MOTION`.
- Workspace continuity: atomic session saves restore notes, recent items, panel visibility, theme, accent, monitor-safe window geometry, project IDs, open editor paths, tabs, renderer IDs, and pending task labels.
- Conversation privacy: each application launch starts a fresh Normal Chat instead of restoring old messages. Within the current run, MORICE keeps complete recent turns and resolves references such as `the previous message` (including common typos).
- Settings precedence: the current saved name, response style, emoji preference, and maturity level remain authoritative during follow-up answers, even when older chat text contains different preferences.
- Truth-first disagreement: MORICE rechecks disputed claims and corrects genuine mistakes, but does not concede a supported answer merely because the user insists. Uncertainty is stated honestly instead of hidden.
- Evaluation posture: conversational testing is direct and does not add MORICE-level morality lectures or canned refusals. Filesystem containment, generated-code validation, renderer validation, model-file validation, and confirmation before destructive desktop actions remain enabled because they prevent accidental machine damage rather than censoring answers.
- Safety: sensitive desktop actions use exact, expiring, one-use grants. File search skips dependency/system folders and symlinks; clipboard monitoring is opt-in; automations run registered callbacks only; unsupported previews and sensors fail honestly.

Useful commands:

```text
/workspace
/system
/find project-name
/open "C:\path\to\file.txt"
/folder "C:\path\to\folder"
/site example.com
/launch notepad
/close-app notepad
/screenshot
/play-pause
/next
/previous
/volume-up
/volume-down
/mute
/theme light
/new-window
```

See [`docs/desktop-workspace.md`](docs/desktop-workspace.md) for the UI and
[`docs/phase-3-desktop-environment.md`](docs/phase-3-desktop-environment.md)
for manager contracts, permission behavior, verification, and honest limits.
See [`docs/phase-4-premium-experience.md`](docs/phase-4-premium-experience.md)
for the shared theme, motion, profile, accessibility, layout, chat, composer,
notification, and performance contracts.

## Quick Install

Ready PC app:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-WebRequest https://raw.githubusercontent.com/EONASH2722/MORICE/main/scripts/install-pc-app.ps1 -OutFile install-pc-app.ps1; .\install-pc-app.ps1"
```

This downloads the MORICE PC release package, verifies it, and extracts it to your user folder.

Requirements:

- Windows 10/11
- Python 3.12
- Git
- A GGUF model file, or any Ollama model name installed on your machine
- Optional: a Vosk English model for wake-word recognition

Clone the repo:

```bat
git clone https://github.com/EONASH2722/MORICE.git
cd MORICE
```

Create a virtual environment:

```bat
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install the local model:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-model.ps1
```

The installer places this file in the repo root:

```text
qwen2.5-coder-7b-instruct-q4_k_m.gguf
```

The script tries the MORICE GitHub model release first, then falls back to the public Hugging Face GGUF if the release asset is not available yet. You can also set:

```bat
set MORICE_GGUF_PATH=D:\Models\your-model.gguf
```

Run MORICE:

```bat
python -m morice.pyside_app
```

## Packaged App

Build the Windows app:

```bat
py -3.12 -m PyInstaller -y MORICE.spec
```

Run the packaged build:

```bat
dist\MORICE\MORICE.exe
```

## Model Distribution

The packaged build prefers the local Qwen model you selected. This workspace package uses:

```text
Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf
```

The normal open-source installer downloads the official compatible Qwen file named `qwen2.5-coder-7b-instruct-q4_k_m.gguf`; MORICE will use either file. Models are not committed into normal Git history because GitHub blocks normal files above 100 MiB. Use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-model.ps1
```

Maintainers can prepare split GitHub Release assets with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-model-release.ps1
```

Upload every generated file from `release\model-qwen2.5-coder-7b-instruct-q4-k-m` to this release tag:

```text
model-qwen2.5-coder-7b-instruct-q4-k-m
```

The model release is available here:

```text
https://github.com/EONASH2722/MORICE/releases/tag/model-qwen2.5-coder-7b-instruct-q4-k-m
```

`install-model.ps1` installs the model directly from that MORICE GitHub release.

## Qwen2.5 Coder 7B VRAM Guide

These are practical targets for the base Qwen2.5 Coder 7B Q4_K_M model. The packaged desktop build uses the selected local Qwen GGUF; the installer downloads the official Qwen Q4_K_M file. Exact speed depends on your CPU, GPU, driver, context length, and how many layers you offload.

| VRAM level | Recommended setup | What to expect |
| --- | --- | --- |
| 0-4 GB | CPU mode or very low GPU layers | Runs offline, but slower replies are normal. |
| 6 GB | Q4_K_M with a small/medium context | Usable for chat and light project mode if other apps are not eating VRAM. |
| 8 GB | Q4_K_M with more GPU offload | Good default level for MORICE's base AI. |
| 10-12 GB | Q4_K_M/Q5 with larger context | Smoother project work, longer files, and better multitasking. |
| 16 GB | Higher context and heavier offload | Comfortable for larger code snapshots and longer replies. |
| 24 GB+ | Larger models or multiple local tools | Room to experiment with stronger models while keeping MORICE responsive. |

Tip: if your PC struggles, lower `MORICE_GPU_LAYERS`, lower `MORICE_CTX`, or use the in-app `Change model` feature to pick a lighter GGUF/Ollama model that fits your VRAM limit.

## Model Control

Open the mode panel with the RGB three-line button, then use the `AI model` section.

MORICE supports four practical model routes:

- Type an Ollama model name, for example `qwen2.5-coder:7b`, `deepseek-r1:1.5b`, or your own custom Ollama model.
- Use `Change model` -> `Files` to pick a file from your PC. The picker accepts any file, then MORICE verifies whether it is an AI model. GGUF files can be used directly by this desktop app.
- Use `Detect GPU` to save your GPU and VRAM profile for model-fit checks.
- Use `Change model` -> `Web` to open MORICE's custom liquid-galaxy model browser. It searches trusted Hugging Face GGUF sources and official model pages, auto-detects GPU/VRAM, preloads a best-fit lane, skips split GGUF shards that cannot install as one file, sorts results by detected GPU fit plus model worth, shows each model's speciality/source/license/task details, and displays compatibility, worth, and a run plan before install.
- The run plan tells the user whether the model is recommended, balanced, usable, CPU-assisted, or not recommended on the detected GPU, plus context and GPU-offload guidance.

MORICE validates selected files before saving them. Random files are rejected with a clear error. This desktop build can run GGUF models directly through the bundled llama runner. If a GGUF file is selected, it takes priority. Use `Clear file` to let the typed Ollama model name answer instead.

After a model change, MORICE resets the local GGUF runtime/cache so the next reply loads the newly selected model cleanly. The selected GGUF path, typed Ollama model name, and detected GPU profile are saved in MORICE settings and used on the next reply/model search.

## PC App Release

The packaged Windows app lives in:

```text
dist\MORICE\MORICE.exe
```

For GitHub releases, the app can be uploaded as a split ZIP package, like a PC app bundle:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-pc-release.ps1
```

Upload every generated file from `release\morice-pc-app` to a GitHub release. Users who want the ready app can download the release package; developers can still clone the repo and install manually.

Once the release assets are uploaded, users can install the ready PC app with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-pc-app.ps1
```

The PC app release is available here:

```text
https://github.com/EONASH2722/MORICE/releases/tag/morice-pc-app
```

Manual users can download `pc-app-manifest.json` and all `MORICE-PC.zip.part*` files from that release, join the parts in order into `MORICE-PC.zip`, then extract it.

## Wake Listener

Start the always-listening wake process:

```bat
start-wake-listener.bat
```

Wake behavior:

- Say the saved wake line, for example `wake up son`.
- Or clap twice inside the wake window.
- Either path launches the app if needed and sets MORICE awake automatically.
- Adaptive noise-floor calibration and automatic gain make quiet speech usable on weak laptop and USB microphones without hard clipping.
- Partial Vosk results are combined across audio blocks, so a broken-up `wake ... up ... son` can still match.
- MORICE tries the preferred/default microphone first, then rotates through usable input devices and sample rates if a device is silent or rejects 16 kHz capture.
- Double-clap thresholds follow the learned room noise; two transients are still required to avoid single-noise wakeups.
- Short event de-duplication prevents repeated partial voice matches or extra clap edges from launching MORICE twice.
- It detects both the packaged `MORICE.exe` app and manual Python runs, so it avoids launching duplicates during development.

The wake line can be changed in the MORICE panel. Voice wake requires a local Vosk model; double-clap wake remains available without one.

Wake diagnostics:

```bat
python morice_wake_listener.py --self-test
python morice_wake_listener.py --list-devices
```

Wake configuration:

| Setting | Default | Purpose |
| --- | --- | --- |
| `MORICE_WAKE_SENSITIVITY` | `high` | Use `high` for quiet or inexpensive microphones, `balanced` for ordinary rooms, or `conservative` where sudden background sounds cause false clap detections. |
| `MORICE_AUDIO_DEVICE` | System default | Force a microphone by device index or name. Run `--list-devices` to find valid values. |

The listener accepts common 16 kHz, 44.1 kHz, and 48 kHz capture paths and resamples voice input for Vosk automatically.

### Weak Or Noisy Microphone Troubleshooting

1. Start with `MORICE_WAKE_SENSITIVITY=high`.
2. Run `python morice_wake_listener.py --list-devices` and select the intended microphone with `MORICE_AUDIO_DEVICE`.
3. Keep the listener running briefly so its adaptive noise floor can learn persistent fan noise, electrical hiss, or a noisy USB input.
4. Check `morice_wake_listener.log` for the active device, capture rate, learned noise level, software gain, recognized partial text, and automatic device rotation.
5. Run `python morice_wake_listener.py --self-test` to verify the conditioning, weak-clap, and phrase-matching pipeline.

The software can improve quiet, noisy, clipped, and wrong-rate microphone input, but it cannot reconstruct speech when the microphone delivers no usable signal.

Optional startup install:

```powershell
powershell -ExecutionPolicy Bypass -File install-wake-listener-startup.ps1
```

## Response Style

MORICE is tuned for answers that feel useful without becoming robotic:

- Start with the direct answer.
- Use short headings when structure helps.
- Explain the reason, tradeoff, or next step in plain language.
- Include examples, checks, or commands when they move the task forward.
- Keep personality present, but keep the work clear.

If you want shorter answers, add a style in the panel such as:

```text
short, direct, no extra explanation
```

## Personalization

Open `Panel` to change:

- What MORICE calls you. Default: `All Father`.
- The wake line.
- The reply style.
- Emoji amount: `None`, `Medium`, or `Expressive`.
- Maturity: `None` keeps language clean, `Medium` permits occasional mild profanity, and `Full` permits strong profanity when it fits a blunt response. Every level stays evidence-based and excludes slurs, threats, and targeted humiliation.
- Theme: `Dark` or `Light`.
- App font: choose an installed option or load your own `.ttf`, `.otf`, or `.ttc` file.

The chosen name updates the launch prompt, input placeholder, start/wake messages, and how MORICE addresses you in replies. Appearance preferences persist locally. A custom font is validated by Qt before MORICE accepts it; invalid or non-font files are rejected.

## Modes

Use the RGB three-line button on the left side of the title bar to open the mode panel:

- `Normal chat` for everyday questions and casual use.
- `Project` for building apps, games, websites, tools, scripts, APIs, and mobile app plans.

Project mode is designed for real workspace changes:

- A Project-only setup area that appears after clicking `Project`.
- A closable project workspace for the file tree, green/red diffs, verification, run logs, Git status, and local commands. New file changes reopen it automatically after a manual close.
- A `+` button for choosing or creating a work folder outside the MORICE app folder.
- `Limited to folder`, which keeps project paths and commands inside the chosen folder and refuses path escapes.
- `Full access`, which permits broader requested work but does not bypass confirmation for overwrites, executable runs, package installs, destructive Git operations, or system changes.
- File building: describe the app, game, website, script, or tool you want. MORICE prepares complete files and a green/red patch; the folder changes only after `Apply patch`.
- If no folder is selected, MORICE prepares a safe default work folder outside the app at `~/MORICE Projects/Quick Build`.
- Existing project awareness: MORICE builds a bounded semantic project index and retrieves relevant source files before editing, so it can update references instead of replacing blindly.
- Request contracts: explicitly named languages, frameworks, engines, platforms, dimensions, and product identities are treated as acceptance criteria rather than suggestions.
- Semantic validation: heading-only pages, static game mockups, fake 3D, silent language switching, and unrelated substitute games are rejected before files are written.
- Follow-up continuity: recent project conversation and the current file snapshot are supplied together, so requests such as `add Flappy Bird to it too` edit the existing project instead of turning the new prompt into a replacement heading.
- Honest local fallback building: MORICE can recover selected deterministic projects such as a complete dependency-free Flappy Bird 3D browser game, but it refuses to invent an unrelated generic game when it cannot implement the requested one.
- A right-side `Project changes` panel with green additions, red removals, `Apply patch`, `Reject`, verified `Undo`, automatic source verification, and closable/widenable review controls.
- `Local mode` uses the selected folder and local model only.
- `Online+local` can add web context for current libraries, docs, patterns, and examples.
- Stronger coding behavior for any requested language or framework.
- Typo-aware intent handling, so rough wording is interpreted from chat context.
- Safer build detection, so `chat:`, `ask:`, `question:`, and `explain:` prompts stay as conversation instead of being treated as file writes.
- In Project mode, the composer replaces the `Personalised` button with the current access mode and adds the local/online toggle.
- The Send button stays grey when empty or while MORICE is replying, then switches to a clean ready state when text can be sent.

## Graphs And Simulations

Use natural prompts:

```text
plot y=x^2-4x+3
plot y=sin(x) and y=cos(x)
simulate projectile motion
simulate 300 particles with gravity and collisions
```

MORICE routes these to deterministic engines:

```text
chat prompt -> visualization decision -> renderer selection -> deterministic data -> validation -> inline workspace
```

The AI model may help reason about the problem, but it never draws directly. The renderer manager turns supported instructions into graph data or simulation state, validates that output, and only then inserts a live workspace into chat. Unsupported or failed renderers display an explicit error instead of an imaginary screenshot or placeholder.

The representative rendering-accuracy matrix covers Cartesian, implicit, polar, parametric, and surface graphs; projectile, pendulum, and 3D particle physics; VSEPR chemistry; directed domain diagrams; prompt-faithful numeric charts; all curated schematic families; and local file previews.

## Message Queue

When MORICE is generating, the send button becomes `Steer`.

Type a follow-up and press Enter or click `Steer`; it is added to the queue. Open `Panel` to:

- Move queued messages up or down.
- Remove one queued message.
- Clear the whole queue.

MORICE sends the next queued item automatically as soon as the current reply arrives.

## Web Lookup Chain

Use:

```text
@web your search query
```

`web:` also works. Normal chat stays offline unless a message starts with `@web` or `web:`.

In Project mode, `Online+local` can search automatically for project context. Switch the composer toggle to `Local mode` when you want file/folder-only work.

The chain is:

```text
@web prompt -> web search -> compact source context -> local model -> answer with source URLs
```

## Notes Chain

Default notes folder:

```text
D:\FOOD FOR MORICE
```

Use `@notes` in a message to include local notes.

The chain is:

```text
@notes prompt -> local notes search -> relevant snippets -> local model -> grounded answer
```

## Useful Commands

- `wake up son`
- `precision on` / `precision off`
- `math steps on` / `math steps off`
- `@web <query>`
- `@notes <question>`

## Customize MORICE

Common places to edit:

- UI and animations: `morice/pyside_app.py`
- MORICE personality and reply rules: `morice/core.py`
- Graph and physics instruction engine: `morice/science_engine.py`
- Chart, local-document, and 2D/3D component-schematic engine: `morice/universal_engine.py`
- Visualization registry, queue, validation, caching, and capability reporting: `morice/visualization.py`
- Local model routing and token budget: `morice/llm_client.py`
- Project fallback file builder: `morice/project_builder.py`
- Agent pipeline and execution: `morice/agent_orchestrator.py`
- Typed tools, permissions, history, and undo: `morice/agent_tools.py`
- Intent and model routing: `morice/intent_router.py` and `morice/model_router.py`
- Project indexing and semantic retrieval: `morice/project_index.py`
- Model verification/search/VRAM scoring: `morice/model_catalog.py`
- Wake listener sensitivity and magic words: `morice_wake_listener.py`
- Saved personalization settings: `morice/settings.py`
- Logo and verified UI captures: `morice/assets/` and `docs/screenshots/`
- Build bundle: `MORICE.spec`
- Strict TypeScript renderer core and tests: `vnext/`

Useful environment variables:

- `MORICE_GGUF_PATH` sets a specific GGUF path.
- `MORICE_MODEL` sets an Ollama model name and bypasses the GGUF default.
- `MORICE_MAX_TOKENS` controls each reply chunk. Default: `6144`. MORICE continues automatically when a compatible endpoint reports a length stop.
- `MORICE_LLAMA_SERVER` set to `1` to use bundled llama-server.
- `MORICE_CTX` sets context length.
- `MORICE_GPU_LAYERS` sets GPU layers.
- `MORICE_THREADS` sets CPU threads.
- `MORICE_BATCH` sets batch size.
- `MORICE_WEB` set to `0` to disable web lookup.

## Project Layout

```text
morice/
  pyside_app.py        Desktop UI
  desktop_environment.py Phase 3 desktop managers, permissions, search, memory, and sessions
  project_builder.py   Local Project mode fallback file generator
  science_engine.py    Deterministic graph, surface, and physics artifacts
  domain_engine.py     Curated molecule and structured-diagram artifacts
  visualization.py     Renderer registry, async pipeline, cache, validation, and capabilities
  core.py              Personality, commands, and helper replies
  llm_client.py        Local/Ollama model routing
  model_catalog.py     Trusted model search, GPU fit scoring, and file verification
  settings.py          Personalization, model choice, wake-line, and GPU profile storage
  web_search.py        Optional web lookup pipeline
  assets/              Logo and bundled app assets
docs/screenshots/      Verified queue, graph, and physics UI captures
docs/vnext-science-workspace.md
scripts/               Model install and release-prep scripts
vnext/                 Strict TypeScript coordinator, cache, graph adapter, and physics core
morice_wake_listener.py
MORICE.spec
Modelfile
```

## Contribute

MORICE is open source under the MIT license. Fork it, change it, and make it yours. Small focused pull requests are easiest to review:

- Describe what changed.
- Mention how you tested it.
- Keep large model files out of Git.
- Do not commit `node_modules`, voice model folders, logs, or private memory files.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development checklist.

## Change The Model To Anything

The base AI is Qwen2.5 Coder 7B, but MORICE is not locked to one brain. Open the mode panel, type any installed Ollama model name, pick a local GGUF with `Change model` -> `Files`, or install one through `Change model` -> `Web`. MORICE saves that choice and uses it on the next reply, so builders can change the model without editing code.

## License

Code: MIT. Models: follow the license for the GGUF model or Ollama model you use.
