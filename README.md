<p align="center">
  <img src="morice/assets/morice-logo-rgb.png" alt="MORICE logo" width="148">
</p>

<h1 align="center">MORICE</h1>

<p align="center">
  <strong>A local-first Windows AI workspace for chat, reviewed project changes, and validated interactive rendering.</strong>
</p>

<p align="center">
  <a href="docs/user-manual.md">User guide</a> &middot;
  <a href="docs/feature-matrix.md">Feature matrix</a> &middot;
  <a href="docs/project-mode.md">Project Mode</a> &middot;
  <a href="docs/vnext-science-workspace.md">VNext rendering</a> &middot;
  <a href="docs/developer-guide.md">Developer guide</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/release-0.7.0--vnext-4f46e5" alt="Release 0.7.0-vnext">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4" alt="Windows 10 and 11">
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776ab" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/UI-PySide6-41cd52" alt="PySide6">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-16a34a" alt="MIT license"></a>
</p>

MORICE is a desktop assistant built around a strict boundary: language models propose, while the host application validates and performs. The selected model can write an answer or produce typed instructions, but MORICE owns file access, renderer execution, desktop permissions, and visible success or failure states. It never treats text such as `[a graph appears]` as proof that an artifact exists.

![MORICE normal chat home](docs/screenshots/morice-home.png)

## Why MORICE

- **Local-first inference:** use a validated GGUF through the local llama runtime or a model served by local Ollama.
- **Normal Chat with real artifacts:** graphs, simulations, molecular views, diagrams, charts, biology models, data structures, schematics, and local file previews appear in the conversation only after host validation.
- **Reviewed project building:** prompts become proposed files and diffs inside a selected work folder, with protected paths and explicit apply controls.
- **Model-independent rendering:** changing the language model does not change the deterministic renderer contract.
- **Desktop workspace:** files, activity, tasks, logs, notes, browser context, media controls, system status, desktop actions, memory, automations, diagnostics, and plugins live behind permission-aware host services.
- **Personal desktop experience:** configurable name, wake phrase, theme, opacity, fonts, emoji amount, response maturity, motion, contrast, text size, and workspace layout.

## Current Application

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/morice-live-graph.png" alt="Validated interactive graph in MORICE"></td>
    <td width="50%"><img src="docs/screenshots/morice-particle-simulation.png" alt="Validated particle simulation in MORICE"></td>
  </tr>
  <tr>
    <td align="center"><strong>Interactive graph</strong><br>Inspection, pan, zoom, reset, and export</td>
    <td align="center"><strong>Live simulation</strong><br>Playback, time control, replay, and state export</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/morice-model-manager.png" alt="MORICE model manager"></td>
    <td width="50%"><img src="docs/screenshots/morice-settings.png" alt="MORICE appearance settings"></td>
  </tr>
  <tr>
    <td align="center"><strong>Model manager</strong><br>GPU-aware run planning and validated model switching</td>
    <td align="center"><strong>Appearance settings</strong><br>Theme, accent, opacity, motion, accessibility, and profiles</td>
  </tr>
</table>

Screenshots were checked against the packaged Windows build at commit `1d464af`. See the [screenshot inventory](docs/screenshots/README.md) for provenance.

## Verified Capabilities

### Conversation

- Full-width user and MORICE messages with long-response continuation safeguards.
- Conversation-aware model prompts, saved response style, optional notes context, and queued follow-up messages.
- Normal Chat starts with a clean visible conversation; persistent memory is separately scoped and managed through Tools.
- Adaptive wake-listener diagnostics and configurable address/wake phrase when microphone dependencies are available.

### VNext Visualization

| Renderer | Verified deterministic scope |
| --- | --- |
| Graph | Multiple Cartesian functions, piecewise, polar, parametric, implicit, Mandelbrot, and linked 2D/3D surfaces |
| Physics | Particles, projectile motion, pendulum and double pendulum, springs, waves, circular/orbital motion, and Lorenz attractor |
| Chemistry | Curated molecular structures and supported VSEPR geometries with shared 2D/3D atom/bond state |
| Biology | DNA, neuron, and cell educational models with labels and 2D/3D views |
| Data structures | BST, AVL, graph, linked list, queue, stack, and hash-table operations with highlights and complexity |
| Charts | Bar, line, pie, scatter, and histogram charts from explicit numeric prompt data |
| Diagrams | Structured domain templates for flows, timelines, networking, OS, databases, AI, security, circuits, biology, and engineering |
| Schematics | Educational component layouts using validated box, sphere, and cylinder primitives; not manufacturing CAD |
| Documents | Local text, source, Markdown, JSON, CSV, image, and PDF previews for valid local paths up to 32 MB |

Unsupported or unparseable inputs produce a visible **Visualization unavailable** card. MORICE does not substitute a fake image or a prose claim. Exact coverage and limits are maintained in the [feature matrix](docs/feature-matrix.md).

### Project Mode

1. Select or create a work folder.
2. Choose **Limited to folder** or **Full access**.
3. Choose local or **Online+local** context.
4. Describe the project, language, framework, and constraints.
5. Review proposed files, red/green diffs, build output, tests, and Git status.
6. Apply or reject the validated change set.

Project Mode accepts arbitrary text-based languages and frameworks; quality still depends on the selected model, available toolchain, and prompt. Its local fallback builder covers a smaller set of web-project patterns when the model does not return valid project JSON. Read the [Project Mode guide](docs/project-mode.md) before enabling broader access.

## Model Support

| Source | Status | Notes |
| --- | --- | --- |
| Local GGUF | Supported | Selected in-app, format-checked, and served through the local llama runtime |
| Local Ollama | Supported | Uses an installed local Ollama service and available local model tags |
| OpenAI-compatible local llama endpoint | Internal runtime | Used by MORICE's bundled local server path |
| Hosted OpenAI, Anthropic, or other cloud APIs | Not integrated in this release | Do not enter provider API keys; use local GGUF/Ollama |

The release lane targets a Qwen2.5 Coder 7B Q4 GGUF. Actual fit depends on context length, GPU layers, driver overhead, and competing GPU workloads.

| Dedicated VRAM | Practical starting point |
| ---: | --- |
| 0-3 GB | CPU-first or small partial offload; expect slow generation and use adequate system RAM |
| 4 GB | Conservative context and partial offload |
| 6 GB | Recommended balanced lane for the release model |
| 8 GB | Comfortable full-offload target with more context headroom |
| 12 GB+ | Headroom for longer contexts or a larger replacement model |

Use **Panel > Change model** to select a model suited to your hardware. See [Models and performance](docs/model-guide.md).

## Install

### Windows installer

Download `MORICE-Setup-0.7.0-vnext.exe` and every adjacent numbered `.bin` slice from the same release into one folder, then run the setup executable. Installation is per-user and does not require administrator access.

### Portable package

Download every `MORICE-0.7.0-vnext-portable.zip.part*` file, the `.parts.json` manifest, and `MORICE-0.7.0-vnext-portable-reassemble.ps1`. Run the reassembler, extract the verified ZIP, and launch `MORICE.exe`.

Always verify downloads against `checksums.json`. Full instructions are in the [user manual](docs/user-manual.md).

### Run from source

```powershell
git clone https://github.com/EONASH2722/MORICE.git
cd MORICE
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python morice_app_launcher.py
```

The repository does not track llama runtime binaries. A local GGUF may exist in a developer checkout but is excluded from Git; choose your own validated model in the app or use Ollama.

## Repository Map

```text
MORICE/
|-- morice/                 Desktop UI, agent pipeline, renderers, tools, and services
|-- vnext/                  Strict TypeScript visualization contracts and tests
|-- tests/                  Python unit, integration, renderer, UI, and safety tests
|-- docs/                   User, architecture, renderer, plugin, and release guides
|-- scripts/                Build, lint, release, and verification automation
|-- installer/              Inno Setup sources
|-- desktop/                Desktop integration assets
|-- third_party/            Redistributable notices and approved runtime material
|-- morice_app_launcher.py  Source entry point
|-- MORICE.spec             PyInstaller application specification
`-- requirements.txt        Python runtime dependencies
```

`build/`, `dist/`, `release/`, caches, local models, and virtual environments are generated locally and are not source artifacts.

## Build And Verify

```powershell
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

Create verified Windows release assets with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

The release script builds the PyInstaller application, portable Zip64 package, split installer assets, and SHA-256 metadata only after its configured checks pass.

## Documentation

- [Documentation index](docs/README.md)
- [User manual](docs/user-manual.md)
- [Feature matrix](docs/feature-matrix.md)
- [Models and performance](docs/model-guide.md)
- [Project Mode](docs/project-mode.md)
- [Advanced configuration](docs/advanced-configuration.md)
- [VNext rendering](docs/vnext-science-workspace.md)
- [Architecture](docs/architecture.md)
- [Plugin SDK](docs/plugin-sdk.md)
- [Developer guide](docs/developer-guide.md)
- [Frequently asked questions](docs/faq.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Release notes](docs/release-notes-0.7.0-vnext.md)

## Contributing And Security

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Use the issue templates for reproducible bug reports and feature proposals. Security problems should follow the private process in [SECURITY.md](SECURITY.md), not a public issue.

MORICE is local-first, not permission-free. Folder boundaries, protected paths, artifact validation, plugin isolation, and sensitive-action confirmations remain active even when broader Project Mode access is selected.

## License

Released under the [MIT License](LICENSE).
