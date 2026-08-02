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
python -m compileall -q morice
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

Then check:

- The app opens with the centered composer.
- The wave background is visible.
- The composer drops to the bottom after the first prompt.
- The queue can add, reorder, remove, and auto-send messages.
- Two claps or the configured wake line wakes MORICE.
- Every successful renderer mounts a real interactive workspace.
- Every failed or unsupported renderer states that nothing was rendered.
- Project Mode previews an exact diff before applying workspace changes.

Plugin platform checks:

```bat
python -m unittest tests.test_plugin_platform -v
python -m morice.plugin_cli validate path\to\plugin
```

Plugin authors should use namespaced contribution IDs, declare only the
permissions they need, and keep renderer output deterministic. See
`docs/plugin-sdk.md` for the manifest, lifecycle, isolation, marketplace, and
diagnostics contracts.

## Style Notes

- Keep UI changes in `morice/pyside_app.py`.
- Keep personality and command behavior in `morice/core.py`.
- Keep wake-listener sensitivity in `morice_wake_listener.py`.
- Keep deterministic renderers behind `morice/visualization.py` and typed artifact modules.
- Keep extension contracts in `morice/plugin_sdk.py`; plugins must not import
  private UI internals.
- Prefer small, readable functions.
- Add positive, negative, and cross-routing tests for every renderer.
- Do not commit large model files, `node_modules`, voice models, logs, or private memory files.
