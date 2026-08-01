# Troubleshooting

## MORICE Does Not Start

- Run `MORICE.exe` from the extracted portable folder, not from inside the ZIP.
- Keep `_internal`, the bundled model, and `MORICE.exe` together.
- Verify the download against `checksums.json`.
- Install current GPU drivers and the Microsoft Visual C++ runtime.
- From source, use Python 3.12+ and install `requirements.txt` in a clean virtual environment.

## Model Returns Nothing

MORICE now shows an explicit empty-response error rather than a blank assistant bubble. Retry once,
reduce the prompt/context size, close VRAM-heavy applications, or choose a different model. Check
the model manager's run plan and application logs.

## Visualization Unavailable

This means no validated artifact was mounted. Read the error card; it will name a parse failure,
unsupported renderer, missing path, or runtime error. Use an explicit equation, molecule name,
numeric data set, or supported simulation type. MORICE does not replace failures with fake output.

## Wrong Renderer Selected

State the visual type directly: `plot`, `simulate`, `render molecule`, `visualize data structure`,
or `open local file`. Include the actual equation, object, numeric values, or valid path. Renderer
predicates are tested to keep dashboard labels such as `Current Time` from becoming clock requests.

## Project Mode Does Not Write Files

- Select a work folder with `+`.
- Do not select the MORICE installation folder.
- Review the proposed patch and press Apply.
- In folder-limited mode, keep all requested paths under the selected root.
- If the model returns invalid JSON, MORICE attempts repair and then a deterministic fallback where supported.

## Wake Phrase Is Missed

```powershell
python diagnose-wake-listener.py
```

Check Windows microphone privacy access, choose the correct input, reduce background audio, and
run calibration again. Very low-quality or noise-cancelled headset inputs can still clip speech.

## Build Verification

```powershell
python -m compileall -q morice
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

For a release build, use `scripts\build-release.ps1`; do not package an old `dist\MORICE` folder.
