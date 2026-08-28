# MORICE Architecture

MORICE is a PySide6 Windows desktop application with host-owned execution boundaries. Language models can propose text, project manifests, or visualization instructions; they cannot directly draw widgets, mutate files, control the desktop, install plugins, or publish Git changes.

## Request Flow

```text
Composer input
  -> deterministic command and capability checks
  -> intent and mode routing
  -> bounded conversation / notes / optional web context
  -> selected local model or host artifact builder
  -> response, typed visualization, or project manifest
  -> family-specific validation
  -> visible result, review surface, or explicit failure
```

![MORICE workflow](morice-workflow-chain.svg)

## Desktop Layers

| Layer | Primary modules | Responsibility |
| --- | --- | --- |
| Window and conversation | `pyside_app.py`, `premium_ui.py` | Title bar, composer, chat rows, settings, model UI, Lab, Project review, notifications |
| Tools workspace | `ui_workspace.py` | Dashboard, files, activity, tasks, logs, notes, browser, media, desktop, and platform tabs |
| Conversation policy | `core.py`, `capabilities.py` | Deterministic replies, capability inventory, context-aware policy, visible-response guarantees |
| Model runtime | `llm_client.py`, `llama_server.py`, `model_catalog.py` | Local GGUF/llama endpoint, Ollama, model validation, catalog and run plans |
| Agent pipeline | `agent_runtime.py`, `agent_planner.py`, `agent_tools.py` | Typed requests, routing, tool plans, workspace facts, telemetry, and recovery |
| Project Mode | `project_builder.py`, `project_runtime.py`, `project_index.py` | Snapshot, manifest validation, semantic checks, diff, atomic apply/undo, test and Git output |
| Autonomous project evidence | `project_workflows.py`, `autonomous_builder.py` | Engine/tool discovery, target state, milestones, exact artifact checks, bounded build/test execution and durable evidence |
| Device network | `node_protocol.py`, `runtime_services.py`, `android/` | Encrypted pairing, node identities, directional capabilities, remote task routing and Android companion |
| Response delivery | `response_policy.py`, `voice_runtime.py` | Truthful deterministic acknowledgements and context-sensitive ElevenLabs delivery hints |
| Visualization | `visualization.py`, `science_engine.py`, `domain_engine.py`, `educational_engine.py`, `universal_engine.py` | Selection, typed artifacts, deterministic builders, validation, scheduling, caching, and workspace data |
| Platform services | `platform_services.py`, `runtime_services.py`, `desktop_environment.py` | Memory, automations, permissions, diagnostics, recovery, updates, backups, desktop actions |
| Plugins | `plugin_sdk.py`, `plugin_manager.py`, `plugin_ui.py` | Manifests, contribution points, process isolation, permissions, updates, marketplace and diagnostics |

## Visualization Boundary

`RendererRegistry` owns stable renderer IDs. `VisualizationManager` decides, queues, sanitizes, validates, caches, and reports each job. The model does not draw. A successful result contains a family-specific `ScienceArtifact`; a failed job contains a renderer ID, stage history, and error.

The Python host is authoritative for the packaged desktop UI. `vnext/src/` supplies strict TypeScript contracts and tested orchestration primitives for the evolving visualization layer.

## Project Boundary

Project Mode resolves paths against the selected root, protects MORICE application paths, validates model JSON and file semantics, previews diffs, and applies writes atomically after review. Full access expands the eligible path scope but does not disable these controls.

## Platform And Plugin Boundary

Desktop and platform operations pass through permission-aware services. Sensitive actions require confirmation. Plugin packages are validated, assigned declared capabilities, and run outside the main application process; crashes and timeouts are recorded without bringing down the UI.

## MORICE Node Boundary

Each enrolled installation advertises a versioned descriptor and structured capabilities. Pairing
uses a time-limited user-opened window, authenticated P-256 key agreement, a compared verification
code, and AES-GCM task envelopes with replay and endpoint checks. Inbound and outbound permissions
are distinct: authorization to query a PC does not authorize that PC to use a phone camera.

LAN discovery advertises availability but never creates trust. The current transport is framed TCP
on a local network; BLE and an end-to-end encrypted relay remain future transports behind the same
message schemas. Android stores peer material through Android Keystore and Windows uses DPAPI.

## Persistence

User settings, scoped memory, platform records, recovery data, and plugin state live in MORICE application-data directories. The visible chat starts clean; durable memory and project records are explicitly queried through their services. Model files and local work folders remain outside the repository and application source tree.

## Failure Principles

- Empty model output becomes a visible error, never a blank assistant success.
- A visualization is successful only after artifact validation and widget mounting.
- A project is changed only after manifest validation and apply.
- A local file preview must reference an existing unchanged file and respect the size limit.
- An unsupported capability is reported as unsupported, not simulated with prose.
