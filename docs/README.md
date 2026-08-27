# MORICE Documentation

This documentation describes the current `0.8.0` Windows application. Claims are tied to source code, tests, real hardware checks, or packaged-build UI inspection; planned capabilities are not presented as shipped features.

## Start Here

| Guide | Use it for |
| --- | --- |
| [User manual](user-manual.md) | Installation, first launch, chat, visuals, settings, and everyday workflows |
| [Feature matrix](feature-matrix.md) | Exact implemented, conditional, and unavailable capabilities |
| [Models and performance](model-guide.md) | GGUF/Ollama setup, GPU fit, and tuning |
| [Project Mode](project-mode.md) | Folder access, project generation, review, apply, tests, and Git status |
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

- [Release notes](release-notes-0.8.0.md)
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
