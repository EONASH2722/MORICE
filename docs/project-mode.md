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
  -> user apply/reject decision
  -> atomic writes
  -> build, tests, logs, and Git status
```

The model is asked for file content, not a tutorial telling the user what to copy. Invalid manifests do not overwrite existing source.

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

The selected project can reference broader filesystem locations. Protected application paths, validation, plugin isolation, and confirmations for sensitive actions remain active. Full access is not a promise that every request will be executed without review.

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

The host can write any text-based language, but it cannot guarantee that an unavailable compiler, SDK, service, signing identity, device, or proprietary asset exists. When a model fails to produce valid project JSON, the built-in fallback is intentionally narrower and primarily covers selected web-project patterns.
