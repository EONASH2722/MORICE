# Feature Matrix

This matrix is the release boundary for MORICE `0.8.0`. It is intentionally narrower than MORICE's long-term roadmap.

## Desktop And Conversation

| Capability | Status | Evidence or condition |
| --- | --- | --- |
| Normal Chat | Supported | Full-width conversation and composer in the PySide6 desktop app |
| Live Action workspace | Supported | Explicit camera-centered voice mode using the same transcript, chat, renderer, Lab, Tools, desktop-action, and project-build pipelines; the camera remains permission-first and memory-only |
| Long reply continuation | Supported | Reply pipeline detects incomplete/empty completion states and keeps a visible result |
| Conversation context | Supported | Recent messages and response settings are supplied to the selected local model |
| Clean visible chat on launch | Supported | The conversation surface starts new; persistent memories are managed separately |
| Personal name and wake phrase | Supported | Panel personalization controls |
| Themes, custom fonts, emoji amount, maturity | Supported | Panel and Settings appearance controls |
| Motion, contrast, large text, interface scale | Supported | Accessibility controls and settings profiles |
| Message queue and steer while replying | Supported | Queue controls and active-response composer |
| Live Action isolation | Supported | Camera, STT, TTS, visual frames, and short visual memory are session-only; leaving stops/cancels and clears them |
| Live camera preview | Supported, local | Real Qt Multimedia device discovery, format selection, reconnect/error state, mirror, memory-only frames, and explicit activation |
| On-demand visual inference | Supported, local | llama.cpp multimodal provider with fresh-frame and quality gates; no visual claim is produced when processing fails |
| Scene awareness | Optional, local | Lightweight scene-change tracking only; disabled by default and never runs the visual LLM per frame |
| Visual targeting | Conditional | Drawn only when the visual provider returns a valid normalized region; otherwise no box is shown |
| Background wake listener | Supported, local | Installed startup listener recognizes MORICE, configured magic words, and double-clap; launches minimized without taking focus, never starts the camera, and yields microphone ownership to Live Action |
| Speech-to-text | Supported, local | Vosk conversation input in Live Action; requires the bundled model, audio device, and Windows permission |
| Text-to-speech | Conditional | ElevenLabs streaming PCM in Live Action; requires a securely configured API key and network access |
| Context-aware speech delivery | Supported | Verified actions use short truthful acknowledgements while explanations and warnings use distinct pace/stability/style metadata; a failed action is never spoken as complete |

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
| Full access selection | Supported | Routine validated project writes apply atomically; sensitive/destructive actions still require confirmation |
| Prompt-to-file manifest | Supported | Model output must satisfy project JSON and semantic validation |
| Red/green diff review | Supported | Mandatory before apply in folder-limited mode; retained as an audit view after Full access writes |
| Atomic file application and undo | Supported | Validated writes with rollback path |
| Build/test/terminal output | Supported | Output panel records commands and results |
| Persistent process evidence | Supported | The expandable process panel remains available after completion and shows routes, detected tools, files, commands, and verification—not private chain-of-thought |
| Git status | Supported | Requires a valid project folder with Git installed where applicable |
| Online+local context | Conditional | Requires network access and only adds retrieved context; it does not grant cloud execution |
| Any text-based language/framework | Model-dependent | The host can write arbitrary text files; generation quality and runnable output depend on the model and local toolchain |
| Engine/framework discovery | Supported | Detects Unreal, Unity, Roblox, Godot, Android, .NET/Visual Studio, Node, Python, Java, Rust, Go, web, and generic projects from real markers and installed tools |
| Durable builder verification | Supported | Goal, target state, milestones, exact artifact checks, bounded build/test output, and repair evidence persist; unavailable editors or playtests are reported separately |
| Local fallback web builder | Supported, limited | Used only when the model fails to return safe project JSON; covers selected web patterns |

## Tools And Platform

| Capability | Status | Notes |
| --- | --- | --- |
| Files, downloads, activity, tasks, logs, clipboard | Supported | Tools workspace tabs |
| Automatic notes and local knowledge | Supported | Relevant indexed notes are selected from natural requests; no special user command is required |
| Automatic web context | Conditional | Freshness-sensitive requests use source-linked web results when connected and fall back locally when offline |
| Goal and capability inference | Supported | Typed goal state is matched against registered tool capabilities and confidence before execution |
| Device intelligence | Supported, local | Normalized device graph, trust metadata, and adapter-backed host observations; unsupported control surfaces fail honestly |
| Network observation | Supported, local | Bounded cached connectivity probe plus local interface reporting |
| Bluetooth discovery | Supported on Windows | Native read-only PnP discovery; driver status is not misreported as an active connection |
| Cross-platform adapters | Windows + Android companion | Windows host control is active. The Android 9+ companion implements its granted node tasks; Linux and macOS remain adapter-ready rather than claimed as controlled |
| Encrypted multi-device nodes | Supported, LAN | Explicit code-confirmed pairing, P-256/HKDF keys, AES-GCM envelopes, replay/timestamp checks, revocation, and separate inbound/outbound capability grants |
| Android companion | Conditional | Unified chat, opt-in voice, foreground Live Vision, device status, media, and application tasks; requires the signed APK and a reachable paired desktop |
| System status and diagnostics | Supported | Health, logs, performance, agent, and component views |
| Memory import/export/search | Supported | Scoped memory service; not the visible chat transcript |
| Automations | Supported | Local automation records with enable/disable controls |
| Desktop actions | Permission-controlled | Host actions are validated and sensitive operations require confirmation |
| Deterministic fast-tool routing | Supported | Routine system/app/media commands record `FAST_TOOL` and zero model invocations |
| Windows application discovery | Supported | Cached Start apps, shortcuts, App Paths, PATH, common locations, running processes, aliases, and ranked fuzzy matching |
| Amazon Music direct search/play | Supported | Semantic accessibility selection plus Windows media-session verification; no hard-coded coordinates |
| Amazon Music transport/metadata | Supported with provider limits | Pause/resume/next/previous/status use Windows sessions with verified media-key fallback; restart position may be unverified |
| Default music provider | Supported | Editable setting; generic music phrases use the selected installed provider |
| Voice diagnostics and microphone test | Supported | Devices, sample rate, level, VAD, transcripts, confidence availability, latency, and non-retained test sample |
| Plugins | Supported | Manifest validation, process isolation, permissions, diagnostics, and contribution points |
| Automatic updater/recovery/backups | Supported | Platform services expose update checks, restore points, and recovery workflows |

## Quality Boundary

Passing validation means the artifact is structurally safe and internally consistent. It does not certify every educational model as laboratory, medical, engineering, or manufacturing truth. Graph coordinates and requested numeric simulation parameters receive stricter numerical tests; generic schematics are explicitly educational.
