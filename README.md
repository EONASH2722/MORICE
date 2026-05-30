<p align="center">
  <img src="morice/assets/morice-logo-rgb.png" alt="MORICE logo" width="150">
</p>

# MORICE

MORICE is a local desktop AI assistant with a PySide6 tinted-glass interface, offline GGUF support, notes lookup, optional web lookup, a wake listener, detailed structured replies, and a reorderable message queue.

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
- Project builder mode with a work-folder picker, folder-limited/full access choices, and stronger coding behavior.
- Chat text is selectable/copyable.
- MIT licensed so anyone can study, change, fork, and customize it.

## Quick Install

Requirements:

- Windows 10/11
- Python 3.12
- Git
- A GGUF model file, or an Ollama model
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

After that, `install-model.ps1` installs the model directly from the MORICE GitHub release.

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

- A work-folder picker for future builds and project-specific answers.
- `Limited to folder`, which keeps project paths and commands inside the chosen folder.
- `Full access`, which treats normal requested project work as pre-approved.
- Stronger coding behavior for any requested language or framework.
- Typo-aware intent handling, so rough wording is interpreted from chat context.

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

`web:` also works. MORICE stays offline unless a message starts with `@web` or `web:`.

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

## License

Code: MIT. Models: follow the license for the GGUF model or Ollama model you use.
