# MORICE Documentation

This documentation covers MORICE `0.11.0`: the integrated GPU globe, White/Pitch Black/Glass themes, chat thinking levels and actual activity receipts, alongside existing natural-language workspace control, rich results, permissions and mathematical replies. Find installers and packages in [Releases](https://github.com/EONASH2722/MORICE/releases). Earlier phase guides retain their own provider and hardware constraints.

The [current location and image validation](spatial-media-validation-0.9.4.md) records the latest checks and concrete limits. The [earlier workspace validation](workspace-validation-0.9.3.md), [Renovation architecture](renovation-architecture.md), [Renovation acceptance report](renovation-report.md) and [135-topic release audit](release-audit-report.md) retain their measured scope.

## Start Here

| Guide | Use it for |
| --- | --- |
| [Globe interface and thinking controls](globe-interface-0.11.0.md) | Integrated globe, three themes, pointer/boot motion, chat effort and real activity |
| [0.11.0 validation](globe-validation-0.11.0.md) | Native evidence, tests, packaging and measured limitations |
| [Reasoning models and mathematical replies](reasoning-math-0.10.0.md) | Primary/fast selection, Qwen3.5 compatibility, offline LaTeX and streamed reply behavior |
| [Natural-language and rich-response guide](nlui-rich-response-guide.md) | Supported conversational workflows, desktop permission and real interactive results |
| [Fast replies and memory](fast-memory-guide.md) | Model selection, whole-chat recall, preferences and privacy |
| [Locations and prompt-only images](spatial-media-0.9.4.md) | Online places, distances, optional references and image readiness |
| [User manual](user-manual.md) | Installation, first launch, chat, visuals, settings, and everyday workflows |
| [Feature matrix](feature-matrix.md) | Exact implemented, conditional, and unavailable capabilities |
| [Models and performance](model-guide.md) | GGUF/Ollama setup, GPU fit, and tuning |
| [Reviewer fixes](reviewer-fixes.md) | Neutral personalization, composer help, Precision behavior, computed graph insights and readable numbers |
| [Projects and Experiments](simple-workspaces.md) | Build and save files, ask about a project, review experiments, and inspect actual results |
| [Project Mode](project-mode.md) | Folder access, project generation, review, apply, tests, and Git status |
| [Android companion](android-companion.md) | APK installation, secure pairing, voice, Live Vision, task grants, and validation limits |
| [Desktop pets](desktop-pets.md) | Animated companions, click-to-open behavior, drag interactions, fullscreen handling, and transparent showcase assets |
| [Scientific research core](research-core.md) | Evidence ingestion, unit-aware calculations, project persistence, exports, named history, and explicit limitations |
| [Research implementation audit](research-core-audit.md) | Before/after evidence and the remaining original-specification gaps |
| [Troubleshooting](troubleshooting.md) | Launch, model, renderer, voice, display, and project problems |
| [FAQ](faq.md) | Short answers about privacy, models, rendering, projects, VRAM, and support |

## Technical References

| Guide | Use it for |
| --- | --- |
| [Architecture](architecture.md) | Desktop process, model pipeline, services, permissions, and storage boundaries |
| [VNext rendering](vnext-science-workspace.md) | Renderer contract, deterministic artifacts, validation, and current families |
| [Advanced configuration](advanced-configuration.md) | Appearance, accessibility, local inference, context, and performance tuning |
| [Plugin SDK](plugin-sdk.md) | Plugin manifests, process isolation, contributions, permissions, and tests |
| [Developer guide](developer-guide.md) | Environment setup, code map, checks, pull requests, and renderer development |
| [Package distribution](package-distribution.md) | Release artifacts, Python package, channel status, checksums, and signing |

## Project Information

- [Current release notes](release-notes-0.11.0.md)
- [Natural-language and rich-response guide](nlui-rich-response-guide.md)
- [Natural-language architecture audit](nlui-rich-response-audit.md)
- [Rich-response capability inventory](rich-response-capabilities.md)
- [0.10.0 local validation report](nlui-rich-validation-0.10.0.md)
- [Earlier 0.8.0 release notes](release-notes-0.8.0.md)
- [Release audit](release-audit-0.8.0.md)
- [Changelog](../CHANGELOG.md)
- [Contributing](../CONTRIBUTING.md)
- [Security](../SECURITY.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)

## Accuracy Policy

MORICE documentation uses three labels:

- **Supported:** implemented and covered by tests or packaged-build inspection.
- **Conditional:** implemented but requires an external local dependency, a valid local file, or a compatible model/toolchain.
- **Not integrated:** absent from the release and intentionally not described as available.

If behavior and documentation disagree, open a bug report with the MORICE version, model source, exact prompt, logs, and a screenshot where useful.
