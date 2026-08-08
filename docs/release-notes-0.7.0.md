# MORICE 0.7.0

MORICE 0.7.0 is the first production-packaged VNext release. It combines local-first
conversation, reviewed project generation, deterministic scientific visualization, model
management, desktop services, and a repeatable Windows release pipeline.

The public documentation and release automation were refreshed for this build. Package metadata,
release-note selection, version checks, hidden-directory auditing, and downloadable filenames are
derived from the release version and verified before publication.

## Major New Features

- Deterministic VNext visualizations directly in Normal Chat.
- Interactive graph, surface, physics, molecule, biology, data-structure, chart, diagram,
  schematic, and document workspaces.
- Project Mode with work-folder selection, exact diff review, validation, output, tests,
  and explicit apply/reject controls.
- In-app GGUF/Ollama model switching with automatic GPU/VRAM compatibility guidance.
- Permission-controlled desktop tools, agent orchestration, local knowledge graph, plugin SDK,
  recovery, verified updates, and release diagnostics.
- A model-bundled Windows installer and portable package plus a model-free Python wheel and
  source distribution for advanced installations.

## Improvements

- Added deterministic routing for benzene, Mandelbrot, Lorenz attractor, double pendulum,
  scientific telemetry dashboards, and Maxwell equation diagrams.
- Dashboard metric labels no longer trigger the date/time shortcut.
- Explicit unsupported visual requests fail visibly rather than becoming model prose.
- Empty model completions produce a clear response and are recorded as failures.
- Visualization completion summaries use the exact job artifact, preventing cross-request text.
- Removed host-appended random emoji and standardized MORICE-native `M//` marks.

## Performance Enhancements

- Hidden render surfaces suspend frame work and release resources when closed.
- Background jobs are bounded, cancellation-aware, and cleaned up at shutdown.
- Shared deterministic state prevents duplicate 2D/3D simulation work.
- The bundled Q4 model supports GPU offload with CPU/RAM fallback based on detected hardware.

## UI Improvements

- Native-style window controls, monitor-safe geometry, responsive workspaces, model/system
  status, themes, fonts, accessibility controls, and reduced-motion support.
- Restored full-width conversation rows for user prompts and MORICE replies.
- Replaced unrelated reaction emoji with compact MORICE-native reaction marks.

## Bug Fixes

- Prevented blank replies when a local model returns an empty completion.
- Prevented fake visualization prose when no validated artifact exists.
- Corrected current-time intent routing inside dashboard prompts.
- Added validated state and stable 2D/3D rendering for supported physics scenes.
- Hardened release packaging against caches, untracked files, local models in developer
  packages, secrets, build logs, and private workspace paths.

## Breaking Changes

- The public version is now the semantic version `0.7.0`; older `0.7.0-vnext` artifact names
  are obsolete and must not be mixed with this release.
- Portable installs must be extracted to a new folder. Do not overlay an old `_internal`
  directory onto the 0.7.0 runtime.
- No intentional Project Mode file-format change is included.

## Installation

### Recommended installer

Keep `MORICE-Setup-v0.7.0-Windows-x64.exe` and all adjacent `.bin` slices in one folder,
then run the executable. Setup is per-user and offers desktop and Start menu shortcuts.

### Portable clean ZIP

Keep all `MORICE-Portable-v0.7.0-Windows-x64.zip.part*` files, the `.parts.json` manifest,
and reassembly script together. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\MORICE-Portable-v0.7.0-Windows-x64-reassemble.ps1`, extract the verified ZIP, and launch
`MORICE.exe` from the extracted `MORICE` folder.

### Python package

Install the downloaded wheel with `python -m pip install <wheel-path>`, then run `morice`.
This lane does not bundle a model; select a local GGUF or Ollama model in the app.

Verify every asset with `SHA256SUMS.txt` or `checksums.json`.

## Upgrade Instructions

Back up important project folders and MORICE settings. Install over the existing per-user
installation, or extract the portable build to a new folder. Re-select any model path that
moved. Do not combine installer slices or portable parts from different versions.

## Known Limitations

- The bundled 7B Q4 model performs best around the 6 GB VRAM class or with CPU/RAM fallback.
- Arbitrary CAD, CFD, medical, quantum-chemistry, and molecular-dynamics requests are not
  general solvers.
- Renderer coverage is deterministic and intentionally rejects ambiguous or unsupported inputs.
- Online+local quality depends on network access and source availability.
- The PyPI, GitHub Packages, WinGet, Chocolatey, and Scoop channels are not advertised until
  publication and publisher verification succeed.
- The Windows binaries are unsigned because no trusted code-signing certificate is configured.
