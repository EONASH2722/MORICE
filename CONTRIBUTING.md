# Contributing To MORICE

Thanks for helping MORICE grow.

## Development Setup

```bat
git clone https://github.com/EONASH2722/MORICE.git
cd MORICE
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Add a GGUF model in the repo root or set `MORICE_GGUF_PATH`.

## Run Locally

```bat
python -m morice.pyside_app
```

Wake listener:

```bat
python morice_wake_listener.py
```

## Before A Pull Request

Run:

```bat
python -m compileall morice morice_wake_listener.py
py -3.12 -m PyInstaller -y MORICE.spec
```

Then check:

- The app opens with the centered composer.
- The wave background is visible.
- The composer drops to the bottom after the first prompt.
- The queue can add, reorder, remove, and auto-send messages.
- Two claps or the configured wake line wakes MORICE.

## Style Notes

- Keep UI changes in `morice/pyside_app.py`.
- Keep personality and command behavior in `morice/core.py`.
- Keep wake-listener sensitivity in `morice_wake_listener.py`.
- Prefer small, readable functions.
- Do not commit large model files, `node_modules`, voice models, logs, or private memory files.
