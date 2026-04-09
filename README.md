# MORICE

![MORICE logo](MORICE%27S%20LOGO.png)

A polished local AI assistant with a glass-style desktop UI, offline GGUF support, and on-demand knowledge lookup. Built to run smoothly on mid-range gaming laptops while still feeling fast, responsive, and human.

Repo: [github.com/EONASH2722/MORICE](https://github.com/EONASH2722/MORICE)

## Highlights ✨
- Glass UI app (PySide6) with smooth interactions and precision toggle.
- Terminal mode for quick workflows. ⚡
- Local models via Ollama or offline GGUF (llama.cpp). 🧠
- On-demand notes with `@notes` and lightweight web lookup. 📚
- Image OCR (text extraction) for screenshots and notes. 🖼️

## Core Strengths
MORICE shines when you want fast, local, practical help without cloud dependence. Its strongest areas are problem solving, code generation, and grounding answers in your own notes.

- Local-first reliability: runs on your machine (Ollama or GGUF) and can work offline.
- Coding and scripting: generates complete, runnable code and practical commands.
- Math and logic: handles equations, step-by-step reasoning, and trick riddles when needed.
- Knowledge grounding: pulls answers from `@notes` and supports lightweight web lookups.
- Clear, actionable output: concise answers with just enough detail to execute.

Tip: the model sets the ceiling. Best results come from Llama 3.1 8B (or higher) with web lookup enabled.

Note: MORICE addresses the primary user as "Father" and treats them as its biological father by design.

## System Requirements
- Windows 10/11 (x64)
- CPU: 4+ cores recommended
- RAM: 16 GB recommended (8 GB minimum)
- GPU: RTX 3050 (6-8 GB VRAM) or better for faster generation
- Disk: ~15-25 GB free if you keep GGUF models locally

## Quick Start (Ollama)
1. Install and run Ollama.
2. Pull a model:
   - `ollama pull llama3:latest`
3. Start MORICE:
   - App: `python -m morice.pyside_app`
   - Terminal: `python -m morice.cli`

## Easy Install (Step-by-Step)
This is the simplest path with the least setup work.

### A) If you want the desktop app only (no coding)
1. Download the latest `MORICE.exe` (Release build).
2. Keep the `MORICE.exe` file in a folder of your choice.
3. Start Ollama and run:
   - `ollama pull llama3:latest`
4. Double-click `MORICE.exe` and chat.

### B) If you want the full source (recommended for updates)
1. Download or clone the repo.
2. Install Python 3.12+ and run:
   - `py -3.12 -m pip install -r requirements.txt` (if you have one)
3. Install Ollama.
4. Pull the model:
   - `ollama pull llama3:latest`
5. Start MORICE:
   - `python -m morice.pyside_app`

## What Files Are Included
This repo contains:
- App source (`morice/`) and UI files
- Launchers (`morice_app_launcher.py`, `morice.cmd`)
- Build files (`MORICE.spec`)
- README + LICENSE

Large model files are not included. You must download them yourself.

## Model Setup (Baby-Easy)
If you can run three commands, you're done:

```bash
ollama pull llama3:latest
ollama serve
python -m morice.pyside_app
```

That's it. MORICE will connect automatically.

## How To Open MORICE (App + Terminal)
### Desktop App (Python)
```bash
cd /d D:\MORICE
python -m morice.pyside_app
```

### Terminal Chat (Python)
```bash
cd /d D:\MORICE
python -m morice.cli
```

### One-Click App (Build)
If you have the build:
`D:\MORICE\dist\MORICE\MORICE.exe`

### Shortcut Command (if you added MORICE to PATH)
```bat
morice
```

## Offline Mode (GGUF)
1. Install the local engine:
   - `py -3.12 -m pip install llama-cpp-python`
2. Download a GGUF model and set the path:
   - `setx MORICE_GGUF_PATH "D:\path\to\model.gguf"`
3. (Optional) Tune performance:
   - `setx MORICE_CTX "4096"`
   - `setx MORICE_GPU_LAYERS "0"` (0 = CPU)
   - `setx MORICE_THREADS "8"`
   - `setx MORICE_BATCH "64"`
4. Run MORICE normally. It will use the GGUF model and ignore Ollama.

## Wake Phrase
Type `wake up son` to activate:

`MORICE is awake`

## Knowledge Notes
MORICE can read your local notes to answer questions.

Default folder:
`D:\FOOD FOR MORICE`

Change it with:
`setx MORICE_KB_DIR "D:\your\folder"`

Notes are on-demand by default: use `@notes` in your prompt.

## Web Lookup
Web lookup is enabled by default and uses DuckDuckGo with Wikipedia fallback.

Example: `@web latest unity 3d version`

Disable with:
`set MORICE_WEB=0`

## Image OCR
The app can extract text from images (OCR). This is for reading text, not full image reasoning.
Image reading is still rough and can miss text; a stronger OCR pipeline is planned.

## Modes
- `precision on` / `precision off` for higher accuracy in code + math
- `math steps on` / `math steps off` for step-by-step math

## Environment Variables
- `MORICE_MODEL` sets Ollama model name
- `MORICE_OLLAMA_URL` sets Ollama base URL
- `MORICE_GGUF_PATH` sets GGUF model path
- `MORICE_CTX` context length
- `MORICE_GPU_LAYERS` GPU layers (0 = CPU)
- `MORICE_THREADS` CPU threads
- `MORICE_BATCH` batch size
- `MORICE_GPU_FALLBACK` set to `1` to fall back to CPU on GPU OOM
- `MORICE_KB_DIR` notes folder
- `MORICE_KB_TOPK` top chunks
- `MORICE_KB_CHUNK` chunk size
- `MORICE_KB_OVERLAP` chunk overlap
- `MORICE_KB_REQUIRE_TAG` set to `1` to only use notes with `@notes`
- `MORICE_KB_PRELOAD` set to `1` to preload notes at startup
- `MORICE_WEB` set to `1` to enable web lookup

## Build the App
If you want a fresh desktop build:

`py -3.12 -m PyInstaller -y MORICE.spec`

## Warning ⚠️
- Models can use a lot of VRAM. If you get OOM, lower GPU layers or use CPU.
- GGUF files are large. Use Git LFS or external hosting for repo storage.
- OCR is text-only; it will not "understand" images like a vision model.

## Roadmap
MORICE is actively evolving. Some parts of the app may still show minor glitches or UI quirks, and there is room for performance and UX upgrades. These fixes and improvements are planned for the near future.

## Contact
Email: `janmeshmeena10@gmail.com`  
WhatsApp/SMS: `+91 8828328565`  
Instagram: `girik2723`

## Licensing
Code: MIT (see LICENSE).

Models: If you use Meta Llama 3.1, you must follow the Meta Llama 3.1 Community License. This repo does not bundle models unless you add them yourself.

---
Built for performance, clarity, and real-world use. 🧩
