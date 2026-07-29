# MORICE Phase 3 Desktop Environment

Phase 3 turns MORICE's desktop helpers into one application-owned integration
layer. The model may request an operation, but operating-system state changes
occur only through a typed manager and a verified result.

## Architecture

`morice/desktop_environment.py` owns independent managers behind
`DesktopIntegrationLayer`:

| Manager | Responsibility |
| --- | --- |
| `DesktopPermissionManager` | Exact, expiring, one-use approval grants |
| `ApplicationManager` | Discovery, launch, close, restart, recent and pinned apps |
| `WindowManager` | Enumerate, focus, minimize, maximize, restore, move, resize and layouts |
| `FileManager` | Semantic search, metadata, recent/large/duplicate files, projects, tags and bookmarks |
| `DocumentManager` | Local text extraction, summaries, entities, formulas, tables and citations |
| `MultimodalContextManager` | Bounded multi-file attachment sets and cross-file search |
| `ClipboardManager` | Session-only opt-in history, classification, search and pinning |
| `NotificationManager` | Persistent priority history and dismissal |
| `MediaManager` | Permission-controlled Windows media-key commands |
| `SystemMonitor` | CPU, RAM, GPU, VRAM, storage, battery, process and thread samples |
| `ScreenshotManager` | Full-screen, window, region and clipboard captures with saved-file validation |
| `MemoryManager` | Bounded scoped memory, retrieval, inspect, pin, archive, delete, import and export |
| `WorkspaceManager` | First-class project state, tasks, editors, Git/build/renderer status and artifacts |
| `SessionManager` | Versioned, bounded workspace restoration data |
| `AutomationEngine` | Registered actions, conditions, variables, delays, bounded repeats and schedules |
| `VoiceManager` | Honest wake/STT/TTS/audio-device capability detection |
| `SearchEverywhere` | Files, projects, memory and pluggable commands, tools and logs |

`RuntimeServices` owns one desktop layer. It starts the automation scheduler,
publishes a desktop snapshot to Diagnostics, and stops monitor/scheduler
threads during clean shutdown.

## Permission Contract

Sensitive actions do not accept a broad permanent switch. The permission
manager fingerprints the action name and exact JSON-compatible payload with
SHA-256. A grant:

- expires after a short interval;
- is consumed once;
- cannot be reused with a changed path, process, window, screenshot region or
  automation;
- is revoked during shutdown.

Application launch, close and restart, window mutation, screenshot capture,
clipboard monitoring, media commands and automation enablement use this
contract. Existing visible buttons or slash commands are direct user requests;
future model-proposed operations must present the grant description before
execution.

## File And Document Intelligence

Semantic file search recognizes type, recency, "yesterday", large-file and
project intent. It uses bounded traversal, skips generated/system directories
and symbolic links, and reports why each result ranked.

Duplicate groups are confirmed with full SHA-256 content hashes after grouping
by size. Preview descriptors provide real metadata and route:

- text, source, Markdown, JSON, XML and CSV to text/table viewers;
- images to the image viewer with dimensions;
- PDF to QtPdf;
- audio/video to QtMultimedia;
- DOCX, XLSX and PPTX to safe ZIP/XML text extraction;
- ZIP to a bounded entry listing.

Document analysis is deterministic and source-linked. It returns extracted
summary lines, entities, formulas, CSV tables and path/line citations. It does
not claim OCR, transcription or PDF text extraction when those backends are
absent.

## Workspace Integration

The Tools dock top search is now Search Everywhere. It combines local files,
registered projects, structured memory, command-palette actions, typed tools
and structured logs. Results retain their real action metadata.

Clipboard monitoring is off by default. The user must approve it for the
current process; its content is not written to desktop state. File previews
consume core preview descriptors, project folders register as first-class
workspaces, and screenshots taken in Project Mode are attached to that
project.

Each application launch still starts a fresh conversation, matching MORICE's
explicit privacy preference. Non-chat workspace data can be restored through
the session manager: projects, editors, tabs, renderers, terminals and pending
task labels. Arbitrary terminal processes are never silently resumed.

## Automation Safety

Automations can invoke only application-registered callbacks. They never
evaluate Python, JavaScript, shell strings or model prose. A workflow supports:

- an exact event or `schedule:interval:<seconds>`;
- a daily `schedule:daily:<hour>:<minute>` event;
- equality conditions against event context;
- `${variable}` substitution;
- delays capped at one day;
- repeat counts capped at 20;
- disabled-by-default persistence;
- explicit one-use approval before enablement.

The initial built-in action is a MORICE notification. Additional actions must
be registered by code and receive their own safety review.

## Performance

Search, system collection and desktop actions are invoked through MORICE's
existing background-task lane. The live monitor and automation scheduler use
daemon workers and stop cleanly. Traversal, history, notification, clipboard,
memory, project and attachment collections all have hard bounds.

## Verified Behavior

`tests/test_desktop_environment.py` verifies:

- exact and one-use permissions;
- approved application launch;
- opt-in clipboard behavior;
- semantic search and project detection;
- byte-verified duplicate groups;
- Office/ZIP extraction and honest malformed-file failure;
- document citations, formulas, entities and tables;
- bounded multi-file cross-reference;
- notification persistence and dismissal;
- relevant scoped memory, export and disable behavior;
- project and session restoration;
- disabled-by-default registered automations, conditions, variables and schedules;
- aggregate Search Everywhere results;
- screenshot approval and saved-output validation;
- runtime capability reporting.

The complete Python suite also covers agent tools, project patch review and
undo, window behavior, wake audio, model routing, and every validated VNext
renderer.

## Honest Limits

- Native application and window control are implemented for Windows.
- Temperature and network-rate fields remain unavailable without a supported
  sensor backend; they are `None`, never invented.
- Current-track metadata and playback position are not available through the
  standard-library media backend. Global playback keys and local Qt playback
  are real.
- PDF pages render through QtPdf, but semantic PDF text extraction requires a
  future installed backend.
- Images expose validated metadata and the existing local viewer. OCR, object
  detection and medical-image interpretation are not claimed.
- Automations intentionally cannot install software, edit the registry,
  reconfigure networking, shut down the PC or execute arbitrary commands.

These limits are exposed through runtime capabilities and error reasons rather
than replaced with simulated success.
