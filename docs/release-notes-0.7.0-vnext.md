# MORICE 0.7.0-vnext

## Major Features

- Deterministic VNext visualizations directly in Normal Chat.
- Interactive graph, surface, physics, molecule, biology, data-structure, chart, diagram,
  schematic, and document workspaces.
- Project Mode with work-folder selection, exact diff review, validation, output, tests,
  and explicit apply/reject controls.
- In-app GGUF/Ollama model switching with automatic GPU/VRAM compatibility guidance.
- Permission-controlled desktop tools, agent orchestration, local knowledge graph, plugin SDK,
  recovery, verified updates, and release diagnostics.

## Reliability Improvements

- Added deterministic routing for benzene, Mandelbrot, Lorenz attractor, double pendulum,
  scientific telemetry dashboards, and Maxwell equation diagrams.
- Dashboard metric labels no longer trigger the date/time shortcut.
- Explicit unsupported visual requests fail visibly rather than becoming model prose.
- Empty model completions produce a clear response and are recorded as failures.
- Visualization completion summaries use the exact job artifact, preventing cross-request text.
- Removed host-appended random emoji and standardized MORICE-native `M//` marks.

## UI And Performance

- Native-style window controls, monitor-safe geometry, responsive workspaces, model/system status,
  themes, fonts, accessibility controls, and reduced-motion support.
- Restored the full-width conversation transcript for both user prompts and MORICE replies; messages
  no longer collapse into detached side bubbles.
- Replaced generic reaction emoji with compact MORICE-native reaction marks.
- Bounded background rendering, resource cleanup, and deterministic state shared by 2D/3D views.

## Installation

- Recommended: keep the Setup executable and all numbered installer slices together, then run Setup.
- Portable: keep every numbered portable part, its `.parts.json` manifest, and the reassembler in
  one folder. Run the PowerShell reassembler, extract the verified Zip64 archive, and run `MORICE.exe`.
- Verify every file with `checksums.json`.

## Upgrade Notes

Back up important project folders and MORICE settings. Install over the existing per-user install
or extract the portable build to a new folder. Existing selected model paths may need to be chosen
again if they moved.

## Known Limitations

- The bundled 7B Q4 model performs best around the 6 GB VRAM class or with CPU/RAM fallback.
- Arbitrary CAD, CFD, medical, quantum-chemistry, and molecular-dynamics requests are not general solvers.
- Renderer coverage is deterministic and intentionally rejects ambiguous or unsupported inputs.
- Online+local quality depends on network access and source availability.

No intentional breaking project-file format change is included in this release.
