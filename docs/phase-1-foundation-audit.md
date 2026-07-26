# Phase 1 Foundation Audit

This document records the stability and architecture work completed for the
MORICE VNext Phase 1 foundation. It is deliberately explicit about remaining
debt: passing tests and a packaged executable do not make every subsystem
fully modular.

## Runtime Architecture

```text
morice_app_launcher.py
        |
        v
RuntimeServices
  |-- StructuredLogManager
  |-- BackgroundTaskManager
  |-- PerformanceProfiler
  |-- StartupHealthChecker
  `-- CrashRecoveryManager
        |
        v
MoriceWindow
  |-- VisualizationManager
  |-- DiagnosticsDialog
  |-- project/chat/model services
  `-- managed background tasks
```

`RuntimeServices` is the lifecycle owner for diagnostics, bounded background
work, crash recovery, startup checks, and clean shutdown. The desktop window
supplies live UI context such as the selected model, detected GPU, renderer
registry, tool registry, task queue, and resource-cache size.

## Audit Findings

| Area | Finding | Phase 1 action |
| --- | --- | --- |
| Main UI | `morice/pyside_app.py` remains a large module with multiple UI surfaces. | Runtime and diagnostics concerns were extracted. Future phases should extract chat, project, model, and visualization widgets independently. |
| Background work | Several ad-hoc daemon threads had no shared visibility or shutdown path. | Routed application tasks through a bounded, named `BackgroundTaskManager`. |
| Logging | Activity messages were visible only in the session UI. | Added searchable rotating JSONL logs with category, level, thread, and metadata fields. |
| Startup | Asset, dependency, settings, model, tool, GPU, and renderer readiness were not validated together. | Added one startup health report with critical and degraded states. |
| Recovery | An unclean exit could lose the active draft and queue. | Added bounded atomic recovery snapshots and crash reports with stack traces. |
| Performance | No shared view of CPU, memory, frame time, FPS, queue depth, or task durations existed. | Added a low-overhead sampler, duration profiler, and diagnostics graphs. |
| Model processes | An owned Ollama or llama-server process could outlive the app after failure. | Added deterministic owned-process cleanup and startup-timeout cleanup. |
| VNext dependencies | The TypeScript package declared physics/rendering libraries that were no longer imported. | Removed unused packages and regenerated the lock file. |

## Diagnostics

Open diagnostics from the side panel, the System tab, or `/diagnostics`.
The dialog includes:

- application, Python, Qt, operating system, model, and GPU details;
- startup health results and critical-failure status;
- renderer/plugin capabilities and unavailability reasons;
- registered tools and active worker names;
- searchable/exportable structured logs;
- CPU, GPU, VRAM, memory, disk-throughput, estimated token-speed, frame-time,
  FPS, queue, and profiler summaries.

Runtime data is stored under `%APPDATA%\MORICE\runtime` by default. Set
`MORICE_RUNTIME_DIR` to isolate it for development or tests.

## Recovery Contract

- Recovery snapshots are written atomically.
- History is bounded to the most recent 160 entries and 8 MiB.
- A clean shutdown removes the session marker and snapshot.
- An unclean shutdown offers recovery on the next launch.
- Unhandled main-thread and worker-thread exceptions are written with stack
  traces before the normal exception hook runs.

## Remaining Architecture Debt

The next extraction targets should be:

1. chat composition, history, and queue state from `MoriceWindow`;
2. Project Mode tree, diff, terminal, and command execution;
3. model browser and local-runtime lifecycle;
4. visualization canvas widgets currently co-located with the desktop window;
5. explicit cancellation tokens for long model and project tasks.

These are follow-up modularity improvements, not hidden Phase 1 completion
claims.

## Verification Contract

Phase 1 is accepted only when:

- Python unit and integration tests pass;
- VNext TypeScript tests, type checking, and dependency audit pass;
- a clean desktop package can be built;
- the packaged executable starts and remains responsive;
- startup health reports no critical failures on the target machine;
- owned workers and model processes stop during clean shutdown.
