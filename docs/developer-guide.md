# Developer Guide

## Environment

- Windows 10 or 11
- Python 3.12+
- Node.js and pnpm for `vnext/`
- Optional local Ollama or a compatible GGUF/llama runtime
- Inno Setup when producing the installer

```powershell
git clone https://github.com/EONASH2722/MORICE.git
cd MORICE
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python morice_app_launcher.py
```

## Code Map

| Area | Main modules |
| --- | --- |
| Desktop shell and chat | `morice/pyside_app.py`, `morice/premium_ui.py`, `morice/ui_workspace.py` |
| Agent pipeline and routing | `morice/agent_runtime.py`, `morice/agent_planner.py`, `morice/agent_tools.py` |
| Models | `morice/llm_client.py`, `morice/llama_server.py`, `morice/model_catalog.py` |
| Project Mode | `morice/project_builder.py`, `morice/project_runtime.py`, `morice/project_index.py` |
| Visualization orchestration | `morice/visualization.py`, `morice/science_engine.py` |
| Desktop/platform services | `morice/desktop_environment.py`, `morice/platform_services.py`, `morice/runtime_services.py` |
| Plugins | `morice/plugin_sdk.py`, `morice/plugin_manager.py`, `morice/plugin_ui.py` |
| Typed VNext core | `vnext/src/` |

## Required Checks

```powershell
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

Run focused tests while iterating, then the complete suite before a pull request. Do not commit generated `build/`, `dist/`, `release/`, caches, virtual environments, model weights, logs, or local settings.

## Renderer Development

A renderer must:

1. expose a stable renderer ID and label;
2. decide whether it can handle a prompt;
3. build a typed `ScienceArtifact` without drawing in the model layer;
4. validate dimensions, topology, finite numeric data, paths, and family-specific invariants;
5. render a real widget;
6. expose an explicit failure when parsing or validation fails;
7. include unit tests for routing, accuracy, UI replacement, interaction, and cleanup.

Never add a prose placeholder as a successful artifact. Educational schematic renderers must label their accuracy boundary.

## Pull Requests

- Branch from the current default branch.
- Keep changes scoped and document user-visible behavior.
- Add or update tests for every behavior change.
- Update the feature matrix when capability boundaries change.
- Replace screenshots only when the visible UI changes.
- Include exact verification commands and results in the pull request.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for style, issue, security, and review expectations.

## Releases

Run `scripts/build-release.ps1`. Verify the installer, portable reassembly, executable launch, assets, icons, documentation, and checksums on a clean Windows user profile. Release notes must identify breaking changes and known limits without claiming planned renderers.
