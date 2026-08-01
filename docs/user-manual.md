# MORICE User Manual

## First Launch

1. Start `MORICE.exe`.
2. Open `Panel` and set how MORICE addresses you, the wake phrase, theme, font, emoji amount,
   maturity tone, accessibility, and motion preferences.
3. Open `Change model` to review the detected GPU/VRAM plan or select another GGUF/Ollama model.
4. Use Normal Chat for conversation and visualization. Use Project Mode only when MORICE should
   create or modify workspace files.

## Normal Chat

Type a message and press Enter or `Send`. The composer is disabled while empty and can accept
queued steering while a long local completion is running. `Precision` requests a more deliberate
answer. `Personalised` applies the saved response style.

Examples:

```text
Plot y = x^3 - 6x^2 + 9x + 15 and mark its extrema.
Render an interactive Mandelbrot set.
Simulate a real-time double pendulum.
Render a complete benzene molecule.
Visualize a binary search tree and show insert, delete, and search.
```

A visualization first shows real generation stages. Success replaces that card with the
interactive workspace. Failure names the renderer problem and states that nothing was shown.

## Project Mode

1. Select `Project` in the left panel.
2. Use `+` to create or select a work folder outside the MORICE installation.
3. Select folder-limited or full access.
4. Select Local or Online+local context.
5. Ask for the complete project or a specific edit.
6. Inspect Files, Changes, Output, Tasks, and Tests.
7. Apply or reject the exact proposed patch.

MORICE can use the language or framework named in the request. A weak or empty model output does
not count as success; MORICE either creates a validated fallback project or explains the failure.

## Model Selection

`Panel > Change model` accepts validated GGUF files and installed Ollama models. The model browser
shows detected GPU memory, compatibility, likely speed lane, license/source metadata, and a run
plan. Close GPU-heavy applications when VRAM is tight.

## Appearance

- Theme: Light, Dark, Midnight, Glass, or Custom.
- Font: built-in choices or a local `.ttf`/`.otf` font selected by the user.
- Emoji amount: None, Medium, or Expressive. This controls model prose, not application icons.
- Maturity: None, Medium, or Full. This changes wording, not factual standards or safety boundaries.
- Motion/accessibility: reduced motion, scaling, larger text, and contrast controls.

MORICE uses its own `M//` visual marks for product states and capability inventories instead of
injecting unrelated emoji after replies.

## Wake Listener

Set a wake phrase in Panel, choose the microphone, and run the wake-listener diagnostic when the
room is noisy or the microphone is quiet. Adaptive gain and learned noise thresholds improve
detection, but microphone quality and Windows privacy permissions still matter.

## Privacy

Local GGUF/Ollama inference, local notes, deterministic rendering, and folder work can remain
offline. Online+local and `@web` intentionally contact external sources. Review project diffs and
sensitive desktop approvals before applying them.
