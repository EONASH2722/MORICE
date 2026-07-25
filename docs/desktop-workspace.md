# MORICE Desktop Workspace

The desktop workspace is MORICE's local UI and operating-system assistance layer. It does not replace or modify the VNext visualization pipeline.

## Architecture

The implementation is split into four focused modules:

- `morice/ui_system.py`: theme tokens and the shared non-blocking animation engine.
- `morice/ui_workspace.py`: command palette, resizable tools dock, previews, dashboard, activity, system, notes, browser, downloads, clipboard, and media surfaces.
- `morice/desktop_assistant.py`: typed command parsing, bounded file search, Windows system inspection, and explicit desktop actions.
- `morice/workspace_state.py`: validated, bounded, atomic session persistence.

`MoriceWindow` connects these modules through Qt signals. File search, system inspection, and desktop execution run away from the UI thread. Results return through Qt's queued signal delivery.

## Workspace Layout

The primary window uses a horizontal `QSplitter`, so the conversation and optional panels can be resized without overlays or fixed blank strips. The Tools dock supports:

- Dashboard with recent conversations and files.
- File explorer, downloads, text preview, JSON tree, image preview, PDF preview, and external-open fallback.
- Activity timeline, queued tasks, live logs, and session-only clipboard history.
- Resource information for CPU, detected GPU/VRAM, memory, storage, battery, device, and local network address.
- Persistent notes.
- Embedded browsing when Qt WebEngine is installed.
- Local Qt Multimedia audio/video playback and Windows media-key controls.

The command palette opens with `Ctrl+K`.

## Appearance And Response Preferences

The `Panel` includes one persistent appearance surface:

- Dark and light theme selection backed by the shared theme-token system.
- Built-in installed font choices plus validated TTF, OTF, and TTC loading.
- None, Medium, and Expressive emoji levels. The preference is included in the model instruction for prose but never modifies code, paths, commands, or structured data.

Font changes are applied to native Qt controls and rich Markdown/KaTeX message views. Invalid files are rejected before the saved selection changes.

Capability inventory questions are handled deterministically by `morice/capabilities.py`. MORICE reports only implemented renderers and tools, tolerates common spelling mistakes in those questions, and keeps real graph or simulation requests on the normal visualization path.

## Persistence

The workspace state is stored in `%APPDATA%\MORICE\workspace-state.json`.

Writes use a temporary file, flush it, and atomically replace the previous state. Loading validates types, text sizes, history length, panel state, and geometry. Restored geometry is clamped to the current primary monitor, so a layout saved on a disconnected display cannot strand the window off-screen.

Clipboard history is intentionally excluded from disk persistence.

Set `MORICE_DISABLE_SESSION=1` to run without loading or saving workspace state. Set `MORICE_REDUCE_MOTION=1` to disable optional motion.

## Desktop Safety

Desktop commands are explicit slash commands rather than model-generated shell execution.

- File and folder opening is non-modifying.
- File search is read-only, bounded, and ignores `.git`, `node_modules`, build output, virtual environments, and Windows system locations.
- Websites are restricted to valid HTTP or HTTPS addresses.
- Application process names are validated.
- `/close-app` always presents a confirmation dialog because unsaved work may be lost.
- No desktop command grants the language model unrestricted shell access.

## Verification

The desktop workspace is covered by `tests/test_workspace_experience.py`, including:

- State round-trip, corruption recovery, and history bounds.
- Sensitive command classification.
- Search-directory exclusions.
- Real system snapshot values.
- Splitter and workspace navigation.
- Command-palette filtering and theme switching.
- Theme, emoji, built-in font, and invalid custom-font behavior.
- Deterministic capability inventories and typo handling.
- Text and JSON inline previews.

The full Python suite also rechecks VNext's graph, physics, chemistry, diagram, Project Mode, and window identity behavior. The TypeScript VNext suite remains independent and is run from `vnext/`.
