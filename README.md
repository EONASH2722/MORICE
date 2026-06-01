<p align="center">
  <img src="morice/assets/morice-logo-rgb.png" alt="MORICE logo" width="150">
</p>

# MORICE

MORICE is a local desktop AI assistant with a PySide6 tinted-glass interface, offline GGUF support, notes lookup, optional web lookup, a wake listener, a real Project builder that writes files into a selected work folder, detailed structured replies, and a reorderable message queue.

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license">
  <img src="https://img.shields.io/badge/python-3.12+-3776ab" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/UI-PySide6-41cd52" alt="PySide6">
  <img src="https://img.shields.io/badge/offline-GGUF-purple" alt="Offline GGUF">
  <img src="https://img.shields.io/badge/base%20AI-Hermes%203%208B-ff6b35" alt="Hermes 3 8B">
  <img src="https://img.shields.io/badge/mode-Project%20Builder-111827" alt="Project Builder">
</p>

<p align="center">
  <img src="docs/screenshots/morice-2026-home.png" alt="MORICE centered launch screen" width="48%">
  <img src="docs/screenshots/morice-2026-panel.png" alt="MORICE personalization panel" width="48%">
</p>

<p align="center">
  <img src="docs/screenshots/morice-2026-queue.png" alt="MORICE chat with message queue panel" width="48%">
  <img src="docs/screenshots/morice-2026-chat.png" alt="MORICE chat screen" width="48%">
</p>

## Highlights

- Tinted-glass desktop app with a centered launch composer.
- Animated purple wave backdrop behind the starting type bar.
- Composer drops to the bottom with a small bounce after the first prompt.
- MORICE defaults to detailed answers with headings, body sections, examples, and next steps.
- Wake listener can launch and wake MORICE with either two claps or magic words.
- While MORICE is replying, use `Steer` to queue follow-up messages.
- Open `Panel` to reorder, remove, or clear queued messages before they send.
- Processing status is shown while MORICE works and disappears when the reply arrives.
- One-command model installer for the Hermes 3 Llama 3.1 8B Q4_K_M GGUF used by this app.
- In-app model picker and Ollama model-name override from the left sidebar, with model-file validation.
- Project builder mode that turns prompts into real files in the selected work folder instead of only printing code.
- Right-side Project changes panel with green/red diffs for files MORICE changed.
- Project `Local mode` / `Online+local` toggle in the composer. Online+local is recommended for current docs and examples.
- Work-folder picker, folder-limited/full access choices, and stronger coding behavior for apps, games, websites, tools, scripts, APIs, and mobile planning.
- Typo-aware and short-form-aware command/intent handling so rough wording like `shrt frm`, `rn`, or `sory` can still be understood from context.
- Liquid Send button animation that only fills when a message is ready to send.
- Chat text is selectable/copyable.
- MIT licensed so anyone can study, change, fork, and customize it.

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
Hermes-3-Llama-3.1-8B.Q4_K_M.gguf
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

MORICE uses:

```text
Hermes-3-Llama-3.1-8B.Q4_K_M.gguf
```

The model is not committed into normal Git history because GitHub blocks normal files above 100 MiB and this GGUF is about 4.9 GB. Use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-model.ps1
```

Maintainers can prepare split GitHub Release assets with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-model-release.ps1
```

Upload every generated file from `release\model-hermes-3-llama-3.1-8b-q4-k-m` to this release tag:

```text
model-hermes-3-llama-3.1-8b-q4-k-m
```

The model release is available here:

```text
https://github.com/EONASH2722/MORICE/releases/tag/model-hermes-3-llama-3.1-8b-q4-k-m
```

`install-model.ps1` installs the model directly from that MORICE GitHub release.

## Hermes 3 8B VRAM Guide

These are practical targets for the base `Hermes-3-Llama-3.1-8B.Q4_K_M.gguf` model. Exact speed depends on your CPU, GPU, driver, context length, and how many layers you offload.

| VRAM level | Recommended setup | What to expect |
| --- | --- | --- |
| 0-4 GB | CPU mode or very low GPU layers | Runs offline, but slower replies are normal. |
| 6 GB | Q4_K_M with a small/medium context | Usable for chat and light project mode if other apps are not eating VRAM. |
| 8 GB | Q4_K_M with more GPU offload | Good default level for MORICE's base AI. |
| 10-12 GB | Q4_K_M/Q5 with larger context | Smoother project work, longer files, and better multitasking. |
| 16 GB | Higher context and heavier offload | Comfortable for larger code snapshots and longer replies. |
| 24 GB+ | Larger models or multiple local tools | Room to experiment with stronger models while keeping MORICE responsive. |

Tip: if your PC struggles, lower `MORICE_GPU_LAYERS`, lower `MORICE_CTX`, or switch the in-app Ollama model name to a lighter model.

## Change Model In App

Open the left sidebar with the three-line button, then use the `AI model` section.

You have two model routes:

- Type an Ollama model name, for example `qwen2.5-coder:7b`, `deepseek-r1:1.5b`, or your own custom Ollama model.
- Use `Change model` to pick a local GGUF file for direct offline chat.

MORICE validates selected files before saving them. Random files are rejected with a clear error. This desktop build can run GGUF models directly through the bundled llama runner. If a GGUF file is selected, it takes priority. Use `Clear file` to let the typed Ollama model name answer instead.

Both the selected GGUF path and the typed Ollama model name are saved in MORICE settings and used on the next reply.

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
- Or clap twice.
- Either path launches the app if needed and sets MORICE awake automatically.

The wake line can be changed in the MORICE panel.

Optional startup install:

```powershell
powershell -ExecutionPolicy Bypass -File install-wake-listener-startup.ps1
```

## Detailed Replies

MORICE is tuned to explain in an easy, detailed style by default:

- Direct answer first.
- Markdown heading.
- Clear body explanation.
- Next heading and body.
- Examples, tradeoffs, checks, or next steps when useful.

If you want shorter answers, add a style in the panel such as:

```text
short, direct, no extra explanation
```

## Personalization

Open `Panel` to change:

- What MORICE calls you. Default: `All Father`.
- The wake line.
- The reply style.

The chosen name updates the launch prompt, input placeholder, start/wake messages, and how MORICE addresses you in replies.

## Modes

Use the RGB three-line button on the left side of the title bar to open the mode panel:

- `Normal chat` for everyday questions and casual use.
- `Project` for building apps, games, websites, tools, scripts, APIs, and mobile app plans.

Project mode includes:

- A Project-only setup area that appears after clicking `Project`.
- A `+` button for choosing or creating a work folder outside the MORICE app folder.
- `Limited to folder`, which keeps project paths and commands inside the chosen folder and asks permission for any specific job outside it.
- `Full access`, which treats normal requested project work as pre-approved while staying private, safe, and non-destructive.
- Real file building: describe the app, game, website, script, or tool you want, and MORICE writes the project files into the selected work folder.
- Existing project awareness: MORICE reads a bounded snapshot of the work folder before editing so it can update files instead of replacing blindly.
- A right-side `Project changes` panel that shows unified diffs with green additions and red removals after each file-building action.
- `Local mode` uses the selected folder and local model only.
- `Online+local` can add web context for current libraries, docs, patterns, and examples.
- Stronger coding behavior for any requested language or framework.
- Typo-aware intent handling, so rough wording is interpreted from chat context.
- In Project mode, the composer replaces the `Personalised` button with the current access mode and adds the local/online toggle.
- The Send button stays grey when empty or while MORICE is replying, then animates with a liquid fill when ready.

## Message Queue

When MORICE is generating, the send button becomes `Steer`.

Type a follow-up and press Enter or click `Steer`; it is added to the queue. Open `Panel` to:

- Move queued messages up or down.
- Remove one queued message.
- Clear the whole queue.

MORICE sends the next queued item automatically as soon as the current reply arrives.

## Web Lookup

Use:

```text
@web your search query
```

`web:` also works. Normal chat stays offline unless a message starts with `@web` or `web:`.

In Project mode, `Online+local` can search automatically for project context. Switch the composer toggle to `Local mode` when you want file/folder-only work.

## Notes

Default notes folder:

```text
D:\FOOD FOR MORICE
```

Use `@notes` in a message to include local notes.

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
- Local model routing and token budget: `morice/llm_client.py`
- Wake listener sensitivity and magic words: `morice_wake_listener.py`
- Saved personalization settings: `morice/settings.py`
- Logo and screenshots: `morice/assets/` and `docs/screenshots/`
- Build bundle: `MORICE.spec`

Useful environment variables:

- `MORICE_GGUF_PATH` sets a specific GGUF path.
- `MORICE_MODEL` sets an Ollama model name and bypasses the GGUF default.
- `MORICE_MAX_TOKENS` controls reply length. Default: `900`.
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
  core.py              Personality, commands, and helper replies
  llm_client.py        Local/Ollama model routing
  settings.py          Personalization and wake-line storage
  web_search.py        Optional web lookup
  assets/              Logo and bundled app assets
docs/screenshots/      README screenshots
scripts/               Model install and release-prep scripts
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

At the end of setup, remember this: the base AI is Hermes 3 8B, but you are not locked to it. In the MORICE app, open the mode panel, type any installed Ollama model name, or pick a different `.gguf` file with `Change model`. MORICE saves that choice and uses it for the next reply, so builders can customize the brain without editing code.

## License

Code: MIT. Models: follow the license for the GGUF model or Ollama model you use.
