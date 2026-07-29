# MORICE User Manual

## Start

Launch `MORICE.exe`. The first-run wizard detects local hardware, recommends a
model class, explains permissions, and creates a workspace. MORICE remains
usable offline.

## Normal Chat

Use Normal Chat for conversation, research, mathematics, science, and inline
VNext visualizations. Supported renderers create real interactive components.
Unsupported requests show an honest renderer error.

## Project Mode

1. Select Project Mode.
2. Use `+` to choose or create a work folder outside the MORICE app folder.
3. Describe the project or change.
4. Review the generated multi-file diff.
5. Apply or reject the exact patch.
6. Inspect Files, Changes, Output, tests, and the Platform dashboard.

Folder-only access contains writes to the selected workspace. Full access
still requires confirmation for destructive desktop and Git operations.

## Platform Dashboard

Open `Tools`, then `Platform`, or use `Ctrl+K` and search for `autonomous
platform`. The page displays project architecture, current runs, knowledge,
update channel, and release readiness.

## Models

Use `Change model` to attach a valid GGUF or select an installed Ollama model.
The model browser compares estimated model VRAM with the detected GPU. The
recommendation is an estimate; actual speed depends on context, quantization,
GPU layers, RAM, and thermal limits.

## Plugins

Open Plugin Center with `Ctrl+K`. Review every requested permission before
enabling a plugin. A plugin runs in a separate process and can be paused,
updated, pinned, rolled back, or removed.

## Backup and Export

The Platform page can export a bounded ZIP bundle. Secure settings and
encrypted backup use Windows DPAPI and can only be opened by the same Windows
user profile.

## Diagnostics

Open `/diagnostics` or select Advanced diagnostics. Inspect startup health,
CPU/RAM/FPS, workers, model status, renderers, tools, agents, plugins, desktop
services, and autonomous-platform state.
