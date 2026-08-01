# MORICE Architecture

MORICE is a local-first PySide6 desktop application. The language model proposes text,
project manifests, or typed visualization instructions. Host-owned services validate and
execute those results.

## Request Flow

1. The intent router checks deterministic commands, safety-critical host responses,
   capability questions, notes/web modes, Project Mode, and visualization intent.
2. Normal text requests are sent to the selected local model with bounded conversation
   context and saved user preferences.
3. Visualization requests enter the renderer registry and never depend on model prose to
   draw a result.
4. Project requests enter the manifest validator and produce a preview before any file is
   changed.
5. Sensitive desktop, Git, plugin, or update actions require the relevant permission and
   validation boundary.

![MORICE workflow](morice-workflow-chain.svg)

## Major Packages

| Package | Responsibility |
| --- | --- |
| `morice/core.py` | Conversation policy, deterministic commands, date/time routing, and visible-response guarantees |
| `morice/pyside_app.py` | Desktop shell, workspaces, chat lifecycle, render canvases, model/project UI, and window behavior |
| `morice/visualization.py` | Renderer registry, selection, async scheduling, progress, validation, and honest failure handling |
| `morice/science_engine.py` | Graph and physics artifact construction |
| `morice/domain_engine.py` | Molecular and structured diagram artifacts |
| `morice/educational_engine.py` | Biology and data-structure artifacts |
| `morice/universal_engine.py` | Charts, component scenes, and local document previews |
| `morice/project_builder.py` | Project contracts, deterministic fallback manifests, and intent validation |
| `morice/agent_runtime.py` | Typed agent request lifecycle and model/tool telemetry |
| `morice/platform_runtime.py` | Desktop services, memory, recovery, plugins, updates, and release diagnostics |

## Trust Boundaries

- Models do not write files directly.
- A visualization is successful only after a typed artifact validates and a workspace is mounted.
- Empty model completions become a visible error response; they are not recorded as success.
- Folder-limited Project Mode resolves every path against the selected workspace root.
- Plugin packages are validated and run outside the main process.
- Downloaded models are checked as model files before becoming selectable.
- Updates are staged and verified before handoff to the updater.

## Persistence

Settings, memory, recovery snapshots, plugin state, and platform data live under the user's
MORICE application-data directories. Chat starts as a new visible session when configured to
do so; durable memory and project state remain separate from the chat transcript.
