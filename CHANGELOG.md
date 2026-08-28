# Changelog

All notable changes to MORICE are documented here.

## [Unreleased]

## [0.8.0-android / 0.8.0-portable] - 2026-08-29

### Added

- Added the MORICE Android companion: unified chat, opt-in voice, on-demand Camera2 Live Vision,
  encrypted device routing, a signed release APK, and no desktop Project Mode.
- Added a versioned multi-node protocol with explicit pairing windows, P-256/HKDF key agreement,
  AES-GCM envelopes, replay protection, directional device-scoped capabilities, LAN discovery,
  Windows DPAPI storage, and Android Keystore storage.
- Added generalized project adapters for Unreal, Unity, Roblox/Rojo, Godot, Android, Visual
  Studio/.NET, Node, Python, Java, Rust, Go, static web, and unknown generic projects.
- Added durable autonomous-builder goal/milestone/evidence state and real available build/test
  execution after exact artifact verification.
- Added deterministic response-state acknowledgements and context-sensitive ElevenLabs delivery
  metadata for brief actions, explanations, and warnings.

### Changed

- Completed processing cards remain available as expandable host-observed execution traces.
- The website now presents Android, secure device networking, generalized Project Mode, and
  separate Android and portable release downloads.

## [0.8.0] - 2026-08-27

### Added

- Added Live Action as a separate camera-centered voice workspace with offline Vosk input,
  interruptible ElevenLabs output, barge-in, glass response overlays, typed input, visual
  rendering, desktop tools, and Project builds.
- Added explicit, memory-only camera capture and on-demand local multimodal inference with
  freshness, quality, and truthful-failure gates.
- Added an installed local background wake listener for MORICE, configured magic words, and
  double-clap, including foreground-safe minimized launch and microphone lease coordination.
- Added deterministic fast routing for Windows applications, system state, media controls,
  Amazon Music search/play, network observation, and Windows Bluetooth discovery.
- Added typed goal state, capability inference, adaptive context selection, device intelligence,
  and cross-platform adapter contracts without claiming unimplemented remote control.
- Added automatic relevant-note selection and freshness-sensitive source-linked web context with
  a local offline fallback; special chat commands are no longer required.
- Added the SmolVLM2 500M vision model/projector pair to packaged Windows builds.

### Changed

- Reduced local reply latency with model prewarm, fast-tool bypasses, bounded context, streaming
  response milestones, and speech prewarm.
- Full-access Project Mode now applies validated routine files atomically instead of presenting a
  success message while leaving the work folder unchanged. Folder-limited mode keeps review.
- Reworked the public site with a responsive Live Action section and accurate automatic-context
  and privacy language.

### Fixed

- Made release-note discovery version-driven instead of hardcoding one release filename.
- Updated version validation for the product-focused README and release download path.
- Generalized package auditing to reject hidden internal tooling directories while preserving
  the public GitHub workflow directory.
- Prevented short background discovery subprocesses from leaking beyond runtime shutdown.
- Made packaged vision use the shared bundled llama resolver and an enforced JSON response format.
- Fixed packaged wake-listener startup, runtime paths, single-instance behavior, and UI-process
  detection. Cold starts are single-flight, noisy partial speech is not accepted as a completed
  wake phrase, scored single-word finals and quiet-separated impulse pairs reject room/game audio,
  native Windows PID checks preserve active Live Action leases, and signal-file contention no
  longer restarts the microphone loop.

### Documentation

- Replaced the implementation-audit-style README with a concise product and installation guide.
- Rebuilt the public README around verified release behavior and explicit capability boundaries.
- Added feature, model, Project Mode, advanced configuration, developer, and screenshot-provenance guides.
- Corrected renderer IDs and removed claims for hosted model providers and unimplemented general-purpose solvers.
- Added a reusable GitHub release template and refreshed current packaged-build screenshots.

### Release Engineering

- Standardized the public version as semantic `0.8.0` from one Python version source.
- Added verified Python wheel and source-distribution packaging with GUI and CLI entry points.
- Added archive policy, secret, split-part, checksum, and package-content audits.
- Added release-validation CI and documented the honest publication status of every package channel.

## [0.7.0] - 2026-08-02

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
