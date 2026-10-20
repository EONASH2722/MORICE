# MORICE Documentation

This documentation describes MORICE `0.9.4`, including the simpler Project and Experiment workflows. Earlier Windows/Android `0.8.0` packages use the previous interface. Each phase guide retains its own provider and hardware constraints.

The [current location and image validation](spatial-media-validation-0.9.4.md) records the latest checks and concrete limits. The [earlier workspace validation](workspace-validation-0.9.3.md), [Renovation architecture](renovation-architecture.md), [Renovation acceptance report](renovation-report.md) and [135-topic release audit](release-audit-report.md) retain their measured scope.

## Start Here

| Guide | Use it for |
| --- | --- |
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

- [Current release notes](release-notes-0.9.4.md)
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
