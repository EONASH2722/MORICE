# Feature Matrix

This matrix is the release boundary for MORICE `0.7.0-vnext`. It is intentionally narrower than MORICE's long-term roadmap.

## Desktop And Conversation

| Capability | Status | Evidence or condition |
| --- | --- | --- |
| Normal Chat | Supported | Full-width conversation and composer in the PySide6 desktop app |
| Long reply continuation | Supported | Reply pipeline detects incomplete/empty completion states and keeps a visible result |
| Conversation context | Supported | Recent messages and response settings are supplied to the selected local model |
| Clean visible chat on launch | Supported | The conversation surface starts new; persistent memories are managed separately |
| Personal name and wake phrase | Supported | Panel personalization controls |
| Themes, custom fonts, emoji amount, maturity | Supported | Panel and Settings appearance controls |
| Motion, contrast, large text, interface scale | Supported | Accessibility controls and settings profiles |
| Message queue and steer while replying | Supported | Queue controls and active-response composer |
| Wake listener | Conditional | Requires working microphone/audio dependencies and OS microphone permission |
| Text-to-speech | Conditional | Depends on installed Windows speech support and configured voice service |

## Model Sources

| Source | Status | Notes |
| --- | --- | --- |
| GGUF file | Supported | Must pass format validation; served through the local llama path |
| Ollama model | Supported | Requires a local Ollama installation/service |
| Hosted model provider APIs | Not integrated | No general OpenAI/Anthropic/cloud API-key workflow in this release |
| Automatic GPU/VRAM detection | Supported | Produces a local hardware estimate and run plan |
| Trusted model browser | Conditional | Catalog browsing and downloads require network access |

## Renderer Families

Every renderer produces typed data, runs host validation, and either displays a real widget or an explicit failure card.

| Family | Status | Current scope |
| --- | --- | --- |
| Graph | Supported | Cartesian, multiple series, piecewise, polar, parametric, implicit, Mandelbrot, and sampled surfaces |
| Physics | Supported | Particle systems, projectile, pendulum/double pendulum, springs, waves, circular/orbital, Lorenz |
| Chemistry | Supported, curated | Recognized curated molecules and VSEPR structures only; unknown molecules fail honestly |
| Biology | Supported, curated | DNA, neuron, and cell educational models |
| Data structures | Supported | BST, AVL, graph, linked list, queue, stack, hash table; insert/delete/search/highlight |
| Numeric charts | Supported | Bar, line, pie, scatter, histogram with explicit numeric data |
| Structured diagrams | Supported, template-based | Flow, timeline, network, OS, database, AI, security, circuit, biology, engineering domains |
| Component schematics | Supported, educational | Validated primitive layouts; not dimensionally certified CAD |
| Local document preview | Conditional | Existing local path; supported text/data/image/PDF types; 32 MB validation limit |
| Rich text and math | Supported | Markdown, tables, code highlighting, KaTeX inline/display math |
| Arbitrary molecular generation | Not integrated | No general cheminformatics structure solver |
| Arbitrary anatomy/CAD/CFD/quantum renderer | Not integrated | Requests outside current deterministic builders fail visibly |

## Project Mode

| Capability | Status | Notes |
| --- | --- | --- |
| Selected work folder | Supported | Required project root and protected app-path checks |
| Folder-limited access | Supported | File operations remain inside the selected root |
| Full access selection | Supported | Broader path scope; validation and sensitive-action controls remain active |
| Prompt-to-file manifest | Supported | Model output must satisfy project JSON and semantic validation |
| Red/green diff review | Supported | Proposed change panel before apply |
| Atomic file application and undo | Supported | Validated writes with rollback path |
| Build/test/terminal output | Supported | Output panel records commands and results |
| Git status | Supported | Requires a valid project folder with Git installed where applicable |
| Online+local context | Conditional | Requires network access and only adds retrieved context; it does not grant cloud execution |
| Any text-based language/framework | Model-dependent | The host can write arbitrary text files; generation quality and runnable output depend on the model and local toolchain |
| Local fallback web builder | Supported, limited | Used only when the model fails to return safe project JSON; covers selected web patterns |

## Tools And Platform

| Capability | Status | Notes |
| --- | --- | --- |
| Files, downloads, activity, tasks, logs, clipboard | Supported | Tools workspace tabs |
| Notes and local knowledge lookup | Supported | Explicit `@notes` context path |
| System status and diagnostics | Supported | Health, logs, performance, agent, and component views |
| Memory import/export/search | Supported | Scoped memory service; not the visible chat transcript |
| Automations | Supported | Local automation records with enable/disable controls |
| Desktop actions | Permission-controlled | Host actions are validated and sensitive operations require confirmation |
| Plugins | Supported | Manifest validation, process isolation, permissions, diagnostics, and contribution points |
| Automatic updater/recovery/backups | Supported | Platform services expose update checks, restore points, and recovery workflows |

## Quality Boundary

Passing validation means the artifact is structurally safe and internally consistent. It does not certify every educational model as laboratory, medical, engineering, or manufacturing truth. Graph coordinates and requested numeric simulation parameters receive stricter numerical tests; generic schematics are explicitly educational.
