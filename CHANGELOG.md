# Changelog

All notable changes to MORICE are documented here.

## [Unreleased]

## [0.9.4] — online places and prompt-only images

- Look up cities, states, countries and other named places through Photon/OpenStreetMap, with bounded requests, a one-day cache and offline GeoNames fallback under existing network permissions.
- Parse distance questions without treating “how far?” as part of a place name. Offer Gujarat, India alongside Gujrat, Pakistan and label representative-point distances clearly.
- Keep snapshots responsive during network lookup and add an explicit Use selected place action for ambiguous results.
- Make reference images and masks optional for prompt-only image generation. Check discovered models when Generate is pressed, show visible readiness errors and prevent duplicate preparation requests.

## [0.9.3] — simpler Projects and Experiments

- Projects selects Builder mode automatically, resolves explicit Build/Ask intent before keyword shortcuts, and uses the bundled chat model when no custom model is selected.
- Keep Project updates and the existing verified browser preview in the Project workspace. Make folder selection, review/save, progress and cancellation explicit.
- Add a plain-language experiment entry and unit-labelled model form, reviewed run plans, persistent results, and visible missing-input errors. Keep specification JSON and diagnostics under Advanced.
- Reduce primary navigation and show labels by default for new sessions. Preserve existing saved navigation preferences and all tool routes.
- Exclude local Python modules and relative imports from inferred pip dependencies. Preserve complete bounded proposal goals or report an oversized request as partial instead of silently truncating requirements.
- Add native file-generation, actual script execution, real experiment, compact-window and shared-runtime regression coverage.
- Keep compact review/save and experiment run controls usable while details scroll. Stop automatic source repair for user/permission/environment verification blocks, and ignore delayed GPU detection after window close.

## [0.9.2] — chat routing repair

- Technical percentages and results no longer trigger exam consolation. Brief personal exam and emotional check-ins still work.
- Mathematical and engineering models no longer trigger MORICE model identity or capability inventory replies. A bare mention of a model no longer requests a visual renderer.
- References to earlier AI answers in a substantive prompt no longer trigger the previous-message recall shortcut.
- Explicit requests not to generate code stay out of the project-file creation path.
- Drain media worker events after process exit so a successful terminal result written between EOF and the exit check is not lost; reject incomplete final events.
- Add regression coverage for the normal and research chat paths, preserving the submitted prompt through selected-model dispatch. See [release notes](docs/release-notes-0.9.2.md).

## [0.9.1] — desktop preview

- Prevent duplicate Research project creation, keep the submitted project title, and preserve a new draft while the request finishes. Queue admission and worker failures allow retry without losing the draft.
- Show an accessible empty state when Settings search has no matches and restore the selected category when results return.
- Normalize permission iterables once so granted medium-risk capabilities do not receive an unnecessary exact confirmation. Denied access and high-risk confirmations remain enforced.
- Refresh the remaining earlier-interface screenshots and publish matching Windows and Python release artifacts. See the [release notes](docs/release-notes-0.9.1.md) for validation and remaining limits.

## [0.9.0] — release candidate

### Added

- Shared Capability Kernel and bounded parallel agent, verified-action, Builder, Research, Mesh, Ambient/Security and Media extensions from the preceding validated phases.
- Renovated desktop Core, original procedural field, authored vector icons, compact composer, workspace navigation and searchable appearance/profile settings.
- Offline GeoNames/Natural Earth Spatial workspace with WGS84 geodesic/chord calculations, context-aware local wake/Spatial commands and explicit provider limits.
- Actual public Activity state, verified artifact inspection and resource-aware media UI.
- Twelve distinct authored theme scenes, a discoverable Glass preset and a direct Theme/animation menu.

### Changed

- Normal app launch and package probes use the same renovated production window factory.
- Existing runtime, permissions, verification, leases and deterministic direct paths remain authoritative.
- Website now reflects the current source UI, offers theme/motion and workspace previews, and distinguishes older public binaries from current source.
- Fine background contours use native antialiased vector paths and smooth cubic curves; only diffuse lighting uses a smaller cached texture. Cycle position and velocity match at restart.
- Core uses the bottom launcher; workspaces use the left sidebar. Only one navigation surface is visible at a time.

### Fixed

- Repeated encoder PATH discovery during Media status polling; diagnostics now use an explicitly labelled cache.
- Media export contract/casing errors, queued voice reply timing, rich-content theme updates and repeated JavaScript declaration scope.
- Large-text category clipping, late effect-clock rearming, closed-window wake polling, and restoration of surviving verified browser bridges.
- Controlled test RAM inconsistency, launching invalid placeholder EXE bytes, native Qt fixture disposal and exact-PID Security fixtures that previously targeted a venv redirector.
- Hidden message editor and native maximize overflow caused by hidden-route height constraints.
- Cold browser-fixture startup and research pause/resume admission races without extending production action deadlines.
- Native icon ownership during worker garbage collection; original artwork now uses bounded native high-DPI icon backing and an explicit proxy-style lifetime.
- Large Research result reads now apply a 500-row SQL page, release readers before JSON decoding and preserve full exports, counts and literal Unicode search.
- Early Windows cancellation now owns the full process family in a private Job before resume; native initial-thread lookup avoids per-system-thread Python stalls while the GUI paints.

### Security and resource ownership

- Existing approval, action observation, cancellation, secret storage, device identity/replay and lease-retention contracts remain in place.
- Model weights and private runtime data are excluded from the model-free distribution; preexisting local weights are retained during local updates.

### Performance and limits

- Measured native UI/idle/startup/paint/raster/soak evidence and exact constructor outliers are documented; no compositor or per-app GPU improvement is claimed.
- Fresh heavy-model and physical hardware checks retain their stated technical constraints. No new public binary release/tag is implied by this candidate.


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
