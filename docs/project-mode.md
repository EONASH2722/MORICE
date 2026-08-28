# Project Mode

Project Mode turns natural-language requests into reviewable workspace changes. It is not a shell with unrestricted silent access.

## Start A Project

1. Open **Panel** and select **Project**.
2. Select `+` under Project setup.
3. Choose or create a folder outside the MORICE application directory.
4. Select **Limited to folder** for the recommended boundary, or **Full access** when the work genuinely spans other locations.
5. Choose local or **Online+local** context.
6. State the deliverable, language, framework, target platform, constraints, and verification command.

![MORICE Project setup](screenshots/morice-project-setup.png)

## Build Pipeline

```text
Prompt
  -> intent and workspace checks
  -> project snapshot and relevant-file selection
  -> optional retrieved web context
  -> coding-model request
  -> typed project manifest
  -> schema, path, and semantic validation
  -> proposed files and diff
  -> folder-limited review, or validated Full access application
  -> atomic writes
  -> exact artifact verification
  -> detected build and tests when available
  -> observed evidence, logs, and Git status
```

The model is asked for file content, not a tutorial telling the user what to copy. Invalid manifests do not overwrite existing source.

## Generalized Project Workflows

Project Mode is not a Roblox-only or web-only builder. It detects project markers and installed
tools for Unreal Engine, Unity, Roblox/Rojo, Godot, Android/Gradle, Visual Studio/.NET, Node.js,
Python, Java/Maven/Gradle, Rust/Cargo, Go, and static web projects. Unknown formats remain usable as
generic projects instead of being forced into an unrelated engine workflow.

The detected adapter supplies only commands declared by the project. For example, an npm build is
not run unless `package.json` actually declares that script, and Python tests are not claimed when
the work folder has no test files. Proprietary editor play mode is reported separately from file or
CLI verification.

Each request creates durable goal, target-state, milestone, attempt, changed-file, and command
evidence. Available build/test commands run after exact file-content verification in Full access.
A nonzero exit or timeout leaves the task in `needs-repair`; it never becomes “done” just because a
model produced plausible prose.

## Visible Process

The processing card remains available as **Show process** after a reply. It exposes host-observed
steps—routing, capability selection, file validation, writes, commands, and verification. This is
an operational audit trail, not hidden model chain-of-thought.

## Review Workspace

- **Project files:** selected tree and file content.
- **Project changes:** added/changed/removed files with green/red diff lines.
- **Project output:** verification, tests, run logs, Git status, and terminal output.
- **Apply/Reject:** explicit change-set decision.
- **Undo:** restores the previous validated state when available.

The review panel can be closed from Project Mode and remains readable during window resizing and splitter transitions.

## Access Modes

### Limited to folder

All project file work is confined to the selected root. Requests requiring another path must return to the user for a specific permission decision.

### Full access

Routine project files are validated and applied atomically without a second Apply click, which keeps the UI's Full access promise. The diff remains available as an audit view. Protected application paths, validation, plugin isolation, and exact one-use confirmations for destructive or sensitive actions remain active.

## Local And Online+Local

- **Local:** project snapshot and selected local model only.
- **Online+local:** adds retrieved current documentation or examples to the model context when network lookup is available.

Online+local does not upload the entire work folder by default and does not provide remote build machines.

## Prompting For Reliable Builds

Good project prompts identify:

- exact deliverable and behavior;
- language, framework, and version;
- target OS/browser/runtime;
- files or modules that must be preserved;
- required assets and whether network downloads are allowed;
- test/build/run commands;
- acceptance criteria.

Example:

```text
Build a playable browser Flappy Bird clone in this folder using TypeScript and Phaser 3.
Create the complete project, not a landing page. Include keyboard and pointer controls,
score, restart, collision, responsive canvas, and unit tests for score/state logic.
Run the tests and report exact files changed.
```

## Limits

The host can write any text-based language, but it cannot guarantee that an unavailable compiler,
SDK, service, signing identity, device, proprietary asset, or GUI automation surface exists. An
editor-aware workflow can identify when Unity, Unreal, Roblox Studio, or another GUI is needed, but
it reports the editor/playtest as unverified until that real application is opened and observed.
When a model fails to produce valid project JSON, the built-in fallback is intentionally narrower
and primarily covers selected web-project patterns.
