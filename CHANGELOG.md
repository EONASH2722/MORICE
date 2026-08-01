# Changelog

All notable changes to MORICE are documented here.

## [Unreleased]

### Documentation

- Rebuilt the public README around verified release behavior and explicit capability boundaries.
- Added feature, model, Project Mode, advanced configuration, developer, and screenshot-provenance guides.
- Corrected renderer IDs and removed claims for hosted model providers and unimplemented general-purpose solvers.
- Added a reusable GitHub release template and refreshed current packaged-build screenshots.

## [0.7.0-vnext] - 2026-08-01

### Added

- VNext typed rendering pipeline and in-chat interactive workspaces.
- Deterministic Mandelbrot, Lorenz attractor, double-pendulum, benzene, telemetry-dashboard,
  and Maxwell-equation renderers.
- GPU-aware model browser and validated in-app GGUF/Ollama switching.
- Project diff review, plugin SDK, desktop services, recovery, update, and release tooling.

### Changed

- Normal Chat owns science visualization; Project Mode remains focused on file-building workflows.
- Capability inventories use MORICE-native `M//` marks rather than unrelated emoji decoration.
- User and MORICE messages once again span the complete conversation row, with MORICE-native
  reaction marks replacing generic emoji reactions.
- Public documentation now separates implemented renderers from explicit limitations.

### Fixed

- Empty model completions can no longer create blank assistant replies.
- Visual requests can no longer silently fall through as fake model descriptions.
- Current-time labels in dashboard prompts no longer hijack intent routing.
- Added validated simulation state and stable 2D/3D rendering for new physics scenes.

### Security

- Preserved host-owned file, renderer, plugin, update, and sensitive-action validation boundaries.
