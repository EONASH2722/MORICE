# Troubleshooting And FAQ

## Installation And Launch

### MORICE does not start

- Extract the portable ZIP fully; do not launch from inside the archive.
- Keep `MORICE.exe` and `_internal` together.
- Verify all parts and `checksums.json` came from the same release.
- Install current GPU drivers and the Microsoft Visual C++ runtime.
- From source, use Python 3.12+ in a clean virtual environment.

### The taskbar icon or title is wrong

Use the current packaged `MORICE.exe`, not an older `dist` folder or pinned shortcut. Remove the old shortcut, rebuild/pin the current executable, and restart Explorer if Windows still caches old metadata.

### Maximized content is cut off

Reset interface scale and workspace layout in Settings. Verify Windows display scaling, then reopen MORICE. Use the standard title-bar maximize button rather than forcing fullscreen through another utility.

## Models And Replies

### MORICE returns no text

Empty completions are converted into a visible failure. Retry once, reduce prompt/context size, close VRAM-heavy programs, inspect logs, or choose another model. A blank model response is never counted as completed work.

### A long answer stops early

Keep the app open until the background status returns to idle. If the model ended at its token limit, ask `continue from the last complete section` or choose a model/context plan with more headroom.

### MORICE identifies the wrong model

The authoritative source is the active-model status and model manager, not the model's self-description. Local models can hallucinate their identity; MORICE's host prompt instructs them not to do so.

### Can I use a hosted API?

General hosted-provider API-key configuration is not integrated in `0.7.0`. Use a local GGUF or local Ollama model.

## Visualization

### Visualization unavailable

No validated widget was mounted. Read the card for an unsupported family, parse error, invalid topology/data, missing file, size limit, or runtime error. Add an explicit renderer type, equation, molecule name, numeric values, units, or valid local path.

### The wrong renderer opens

Use explicit language: `plot`, `simulate`, `render the curated molecule`, `visualize the data structure`, `chart these values`, `draw a flow diagram`, or `preview this local file`. Router tests prevent common dashboard labels from hijacking time/date or file-preview intent, but ambiguous prompts can still need clarification.

### Why does an unknown molecule fail?

Chemistry rendering uses a curated validated structure library. MORICE refuses to invent atom positions for an unknown molecule. General cheminformatics generation is not part of this release.

### Is every 3D schematic dimensionally accurate?

No. Supported component scenes are labeled educational. Numerical graphs and supported physics parameters have stronger accuracy tests; generic schematics are not manufacturing CAD.

## Project Mode

### No files were written

- Select a work folder with `+`.
- Do not select the MORICE installation folder.
- Wait for a proposed manifest and review the diff.
- Press Apply; generation alone does not mutate the workspace.
- Keep folder-limited paths under the selected root.
- Check Project output for invalid JSON, model timeout, missing toolchain, or test failure.

### MORICE built a page instead of the requested game/app

State `create the complete playable application, not a landing page`, name the framework, list required mechanics, and include a runnable acceptance test. Use a coding-focused model. The local fallback builder is narrower than the model-driven project path.

### The review panel will not close

Use the close control on Project changes/Lab, then reset the workspace layout if it remains pinned. The current build includes a regression test for closing Lab during splitter transitions.

## Voice

### Wake phrase is missed

```powershell
python diagnose-wake-listener.py
```

Grant Windows microphone permission, choose the intended input, reduce competing background audio, and recalibrate. Adaptive gain and noise-floor learning improve weak microphones but cannot recover clipped or absent audio.

## Performance

### High RAM or VRAM use

Pause/close active visualizations, reduce particle count, close GPU-heavy applications, use a smaller quantization/context, and restart the model runtime after switching large models. The title bar reports current local resource estimates.

### Simulation slows in the background

Hidden physics canvases are designed to stop consuming simulation frames. Report a bug with the exact renderer, particle count, whether Lab was open, and performance diagnostics if usage remains high.

## Diagnostics

```powershell
python -m compileall -q morice
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

Use `scripts\build-release.ps1` for release packaging. Do not ship an old local `dist\MORICE` directory.
