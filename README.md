<p align="center">
  <img src="morice/assets/morice_logo.png" alt="MORICE logo" width="150">
</p>

# MORICE

MORICE is a local desktop AI assistant with a PySide6 tinted-glass interface, offline GGUF support, notes lookup, optional web lookup, a wake listener, and a reorderable message queue.

<p align="center">
  <img src="docs/screenshots/morice-home.png" alt="MORICE centered launch screen" width="48%">
  <img src="docs/screenshots/morice-queue.png" alt="MORICE message queue panel" width="48%">
</p>

## Highlights

- Tinted-glass desktop app with a centered launch composer.
- Animated purple wave backdrop behind the starting type bar.
- Composer drops to the bottom with a small bounce after the first prompt.
- Wake listener can launch and wake MORICE with either two claps or magic words.
- While MORICE is replying, use `Steer` to queue follow-up messages.
- Open `Panel` to reorder, remove, or clear queued messages before they send.
- Processing status is shown while MORICE works and disappears when the reply arrives.
- Chat text is selectable/copyable.

## Current Setup

- Main engine: `Hermes-3-Llama-3.1-8B.Q4_K_M.gguf`
- Runtime: llama.cpp `llama-server.exe`
- Desktop app: `python -m morice.pyside_app`
- Packaged app: `dist\MORICE\MORICE.exe`
- Wake listener: `start-wake-listener.bat`

MORICE addresses the primary user as `All Father`.

## Start

```bat
cd /d "D:\MORICE - Copy"
python -m morice.pyside_app
```

Or run the packaged build after creating it:

```bat
cd /d "D:\MORICE - Copy"
dist\MORICE\MORICE.exe
```

## Wake Listener

Start the always-listening wake process:

```bat
cd /d "D:\MORICE - Copy"
start-wake-listener.bat
```

Wake behavior:

- Say the saved wake line, for example `wake up son`.
- Or clap twice.
- Either path launches the app if needed and sets MORICE awake automatically.

The wake line can be changed in the MORICE panel.

## Message Queue

When MORICE is generating, the send button becomes `Steer`. Type a follow-up and press Enter or click `Steer`; it is added to the queue. Open `Panel` to move queued messages up/down, remove one, or clear the queue. MORICE sends the next queued item automatically as soon as the current reply arrives.

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

## Environment Variables

- `MORICE_GGUF_PATH` sets a specific GGUF path.
- `MORICE_MODEL` sets an Ollama model name and bypasses the GGUF default.
- `MORICE_LLAMA_SERVER` set to `1` to use bundled llama-server.
- `MORICE_CTX` sets context length.
- `MORICE_GPU_LAYERS` sets GPU layers.
- `MORICE_THREADS` sets CPU threads.
- `MORICE_BATCH` sets batch size.
- `MORICE_WEB` set to `0` to disable web lookup.

## Build

```bat
cd /d "D:\MORICE - Copy"
py -3.12 -m PyInstaller -y MORICE.spec
```

## License

Code: MIT. Models: follow the license for the GGUF model you use.
