# MORICE User Manual

## Install

### Installer

Keep `MORICE-Setup-v0.7.0-Windows-x64.exe` and all numbered installer `.bin` slices from the same release together. Run the setup executable and launch MORICE from the installed shortcut.

### Portable

Keep every portable `.part*` file, the `.parts.json` manifest, and the provided reassembly script together. Open PowerShell in that folder and run `powershell -NoProfile -ExecutionPolicy Bypass -File .\MORICE-Portable-v0.7.0-Windows-x64-reassemble.ps1`. Extract the verified ZIP and launch `MORICE.exe`; do not run it from inside the ZIP or separate the executable from `_internal`.

### Python package

The wheel is a model-free advanced installation. Install the downloaded `morice_ai-0.7.0-py3-none-any.whl` with `python -m pip install <wheel-path>`, then run `morice`. Configure a local GGUF or Ollama model in the application. This release does not claim a public package-manager channel until publication is independently verified.

## First Launch

1. Start MORICE.
2. Open **Panel** and choose how MORICE addresses you and your wake phrase.
3. Review theme, font, emoji amount, maturity, motion, contrast, and scale.
4. Open the mode panel and choose **Normal chat**.
5. Use **Change model** if the configured local model is unavailable or does not fit your hardware.
6. Run **Detect GPU** for a local VRAM estimate.

MORICE opens with a clean visible conversation. Durable memory, project records, and platform data are separate services and do not repopulate the chat transcript.

## Normal Chat

Type a message and press Enter or **Send**. The Send button remains disabled while the input is empty or a non-steerable action is active. During a long local completion, the composer can queue or steer a follow-up instead of creating overlapping replies.

- **Precision:** requests a more deliberate response profile.
- **Personalised:** applies the saved address and response-style instructions.
- **Attach:** selects an image for supported multimodal/context workflows.
- **Voice:** shows voice input and wake-listener status.
- **Model:** opens model selection.
- **Mode:** switches between Normal Chat and Project Mode.
- **Quick actions:** opens common commands and tools.

Use explicit nouns, values, and units. MORICE corrects common spelling errors using conversation context, but precise requests improve local-model results.

## Visualizations In Chat

Visualization is part of Normal Chat, not Project Mode.

```text
Plot y = x^3 - 6x^2 + 9x + 15 and mark its extrema.
Render an interactive Mandelbrot set.
Simulate a double pendulum with g = 9.81 m/s^2.
Render the curated benzene molecular model in 2D and 3D.
Visualize a BST and demonstrate insert, search, and delete.
```

The request moves through analyzing, renderer selection, data preparation, validation, and mounting. A successful progress card is replaced by a real interactive widget. A failure card states that nothing was rendered and gives the parser/validator error.

Controls vary by family: zoom, pan, rotate, hover inspection, 2D/3D switch, pause, resume, step, reset, time scale, vectors, trails, labels, parameter inputs, and export. See the [feature matrix](feature-matrix.md) for exact coverage.

## Project Mode

1. Open the mode panel and select **Project**.
2. Select `+` and choose a work folder outside the MORICE installation.
3. Choose **Limited to folder** or **Full access**.
4. Choose local or **Online+local** context.
5. Ask for a complete project or a concrete edit.
6. Review Project files, Project changes, and Project output.
7. Apply or reject the exact proposed change set.
8. Inspect tests, run logs, terminal output, and Git status.

MORICE asks the coding model for file artifacts rather than instructions to copy and paste. Invalid or unsafe project JSON cannot replace existing files. Read the full [Project Mode guide](project-mode.md).

## Tools Workspace

**Tools** opens a resizable workspace with:

- Dashboard;
- file explorer and downloads;
- activity timeline, tasks, logs, and clipboard;
- platform memory, automations, diagnostics, recovery, updates, and plugins;
- system status, notes, browser context, media, and permission-controlled desktop actions.

Use `@notes` in chat when selected local notes should be included as context. Online lookup is explicit and requires network access.

## Model Selection

The current release supports validated local GGUF files and locally installed Ollama models. The model browser can detect GPU memory, estimate compatibility, display source/license metadata, and prepare a run plan. It does not configure hosted provider API keys.

Changing the model changes reply and coding quality; it does not bypass host rendering, path, or permission checks. See [Models and performance](model-guide.md).

## Appearance And Personalization

- **Theme:** use the exposed Glass/dark/light appearance paths.
- **Font:** choose a bundled family or load a local `.ttf`, `.otf`, or `.ttc` file.
- **Emoji amount:** none, medium, or higher-use model prose.
- **Maturity:** adjusts wording tolerance, not factual standards or safety boundaries.
- **Motion:** select an animation profile or reduce interface motion.
- **Accessibility:** high contrast, larger UI text, interface scale, and layout profiles.

The top-bar sun/moon control switches the active theme. Settings includes search and live preview.

## Voice And Wake Listener

Set the wake line in Panel. Microphone quality is improved through adaptive gain, noise-floor calibration, and diagnostics, but Windows microphone privacy permissions and actual hardware still matter.

```powershell
python diagnose-wake-listener.py
```

If startup listening is wanted, use the provided startup installation script only after confirming the diagnostic works.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Enter` | Send from the active composer when enabled |
| `Ctrl+K` | Command palette / quick actions |
| `Ctrl+O` | Attach an image |
| `Ctrl+,` | Open settings |

## Privacy

Local GGUF/Ollama inference, deterministic rendering, notes search, project work, and local memory can remain on the machine. Online+local and web lookup intentionally access network sources. Plugins have declared permissions and run outside the main process, but users should still install only trusted packages.
