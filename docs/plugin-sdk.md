# MORICE Plugin SDK

MORICE 0.6 introduces a versioned extension platform for tools, renderers,
models, commands, themes, workspaces, voice providers, memory providers, and
automations. Plugins are discovered at startup and run in separate processes.
They do not import themselves into the MORICE UI process.

## Safety Contract

Every plugin has three boundaries:

1. `plugin.json` is parsed and validated before plugin code runs.
2. Requested permissions are shown to the user and stored per plugin version.
3. The plugin runs behind bounded newline-delimited JSON-RPC in a dedicated
   process.

MORICE enforces request and response size limits, call timeouts, safe shutdown,
crash detection, dependency checks, package extraction limits, path traversal
rejection, and core-file write denial. Undeclared file, network, process, and
native-library access is blocked by the host audit layer.

This is strong application-level isolation and crash containment. It is not a
replacement for an operating-system sandbox or virtual machine when running
untrusted native code. MORICE intentionally blocks direct native library
loading from plugins.

## Manifest

Each package contains one `plugin.json` and a relative Python entry point:

```json
{
  "id": "example.science-tools",
  "name": "Science Tools",
  "version": "1.0.0",
  "apiVersion": "1.0",
  "description": "Adds a validated diagram renderer and a calculation tool.",
  "author": "Plugin developer",
  "entryPoint": "plugin.py",
  "license": "MIT",
  "categories": ["renderer", "tool"],
  "permissions": ["notifications"],
  "dependencies": [
    {"id": "example.foundation", "version": "^1.0.0", "optional": true}
  ],
  "platforms": ["any"],
  "minMoriceVersion": "0.6.0",
  "lazy": false,
  "contributions": {
    "commands": [
      {
        "id": "open-science-tools",
        "title": "Open Science Tools",
        "description": "Run the plugin command",
        "keywords": ["science", "extension"]
      }
    ],
    "tools": [
      {
        "id": "example.science-tools.calculate",
        "title": "Science calculator",
        "description": "Perform a plugin-owned calculation.",
        "inputSchema": {
          "type": "object",
          "properties": {"value": {"type": "number"}},
          "required": ["value"],
          "additionalProperties": false
        },
        "outputSchema": {"type": "object"},
        "timeoutSeconds": 10,
        "risk": "read_only"
      }
    ],
    "renderers": [
      {
        "id": "example.science-tools.diagram",
        "title": "Science process diagram",
        "keywords": ["science process"],
        "interactive": true,
        "timeoutSeconds": 20
      }
    ]
  }
}
```

Plugin ids use lowercase letters, digits, dots, and hyphens. Contributions use
stable ids. Tool and renderer ids are global and therefore must be namespaced
to avoid collisions.

## Entry Point

The entry point exports `Plugin` or `create_plugin(api)`:

```python
class Plugin:
    def __init__(self, api):
        self.api = api

    def on_start(self):
        starts = self.api.storage_get("starts", 0)
        self.api.storage_set("starts", starts + 1)
        self.api.log("INFO", "Science Tools started.")

    def on_pause(self):
        pass

    def on_resume(self):
        pass

    def on_stop(self):
        pass

    def on_event(self, event_name, payload):
        self.api.log("DEBUG", event_name, payload=payload)

    def handle_command(self, command_id, arguments):
        if command_id == "open-science-tools":
            if self.api.has_permission("notifications"):
                self.api.notify("Science Tools", "The plugin is ready.")
            return {"opened": True}
        raise ValueError(f"Unknown command: {command_id}")

    def handle_tool(self, tool_id, arguments):
        if tool_id == "example.science-tools.calculate":
            value = float(arguments["value"])
            return {"input": value, "square": value * value}
        raise ValueError(f"Unknown tool: {tool_id}")

    def render(self, renderer_id, prompt):
        return {
            "kind": "diagram",
            "title": "Validated plugin diagram",
            "diagramType": "flowchart",
            "nodes": [
                {"id": "input", "label": "Input"},
                {"id": "result", "label": "Result"}
            ],
            "edges": [
                {"source": "input", "target": "result", "label": "calculate"}
            ],
            "notes": ["Rendered from deterministic plugin data."]
        }
```

The injected `api` also provides bounded helpers:

- `storage_get`, `storage_set`, and `storage_delete`
- `settings_get` and `settings_set`
- `file_read_text`, `file_write_text`, and `file_list`
- `fetch_json` for checksum-independent runtime HTTPS data
- `run_process` with argument arrays, output limits, and no shell
- `notify`, `log`, `emit`, `request_visualization`,
  `request_workspace`, and `request_desktop_action`

Each helper enforces its corresponding reviewed permission. File writes are
atomic and MORICE core paths remain read-only even when a plugin has general
write permission.

Renderer plugins return data, never Qt widgets or executable UI markup. MORICE
converts the JSON into its typed `ScienceArtifact`, validates node ids and
edges, and uses the existing deterministic canvas. Invalid output produces an
honest render failure.

## Lifecycle

Tracked states:

```text
Installed -> Validated -> Loaded -> Running
Running <-> Paused
Running -> Updating -> Validated
Running -> Failed -> Recovery -> Running
Running -> Disabled -> Uninstalled
```

Invalid state transitions are rejected. A failed or timed-out host loses all
registered tools and renderers immediately. Recovery starts a fresh process.
Hot reload watches `plugin.json` and the entry point during development.

## Permissions

Supported declarations:

| Permission | Capability |
| --- | --- |
| `filesystem.read` | Brokered reads outside the plugin package |
| `filesystem.write` | Brokered writes outside plugin storage |
| `network` | Internet or local network access |
| `process` | Brokered process execution |
| `project.read` | Read the active project through MORICE |
| `project.write` | Write to the active project through MORICE |
| `clipboard` | Clipboard access |
| `notifications` | MORICE notifications |
| `microphone` | Microphone input through MORICE |
| `voice` | Voice-provider integration |
| `camera` | Camera input through MORICE |
| `desktop.control` | Desktop interaction through MORICE |
| `model.access` | Active-model requests |
| `memory.read` / `memory.write` | Approved memory provider access |
| `automation` | Plugin automation execution |
| `gpu` | GPU-backed computation |

Declaring a permission does not grant it. The user must review every declared
capability, and decisions are invalidated when the plugin version changes.
Plugin-local key/value storage is available without general filesystem access
and has a 2 MB quota.

## Contributions

The manifest supports:

- `commands`: searchable command-palette actions.
- `tools`: typed agent tools with JSON input/output schemas.
- `renderers`: keyword-selected deterministic diagram renderers.
- `themes`: named Qt stylesheet contributions.
- `workspaces`: sidebar, toolbar, or workspace view declarations.
- `models`: model-provider metadata and sandboxed generation calls.
- `ui`, `toolbarButtons`, `sidebarPanels`, `contextMenus`,
  `workspacePanels`, and `floatingWindows`: declarative native UI surfaces.
- `settings`: plugin-owned settings schema.
- `memory`: memory provider metadata.
- `automations`: permission-controlled automation handlers.
- `voice`: voice provider metadata.

Model backends implement `generate`. Memory providers implement
`handle_memory`, voice providers implement `handle_voice`, and automations
implement `run_automation`. MORICE validates provider ids against the manifest
before making any sandbox call.

MORICE exposes model, theme, workspace, memory, voice, settings, and automation
catalogs through `PluginManager.contribution_catalog()`. Tools and renderers are
registered directly with the existing agent and VNext registries while a plugin
is running.

## Events

Plugins can implement `on_event(name, payload)`. Delivery is asynchronous and
bounded so a slow extension cannot block the UI. Core events include:

- `application.started`, `application.stopping`
- `chat.started`, `chat.finished`
- `project.loaded`, `project.closed`
- `file.opened`, `file.saved`
- `visualization.started`, `visualization.finished`, `visualization.created`
- `renderer.started`, `renderer.finished`
- `model.loaded`, `model.changed`, `model.switched`
- `voice.activated`, `memory.updated`, `workspace.changed`
- `screenshot.captured`, `notification.created`, `automation.triggered`,
  `theme.changed`
- `plugin.installed`, `plugin.removed`, `plugin.loaded`, `plugin.unloaded`,
  `plugin.failed`

Subscriber failures are isolated from the publisher.

## Developer CLI

Create a sample:

```powershell
python -m morice.plugin_cli init .\hello-plugin `
  --id example.hello `
  --name "Hello MORICE"
```

Validate and package it:

```powershell
python -m morice.plugin_cli validate .\hello-plugin
python -m morice.plugin_cli pack .\hello-plugin --output .\hello-plugin.zip
```

Inspect a development runtime:

```powershell
python -m morice.plugin_cli --runtime .\.plugin-runtime list
python -m morice.plugin_cli --runtime .\.plugin-runtime doctor
```

The same generator and packager are available in **Plugin Center > Developer**.

## Marketplace and Updates

Plugin Center accepts a local or HTTPS JSON catalog. Entries can include
verified/featured status, ratings, downloads, category, screenshots,
documentation, and release notes. Downloads require HTTPS and can include a
SHA-256 checksum. Marketplace installs and updates require that checksum and
verify it before extraction.

Updates create an immutable local backup before replacement. Users can pin an
installed version or roll back to any retained backup. Update packages pass the
same validation and permission-review path as new installs.

Compatible marketplace updates can be installed manually or enabled as
background automatic updates. Automatic-update preference is persisted locally.
Pinned plugins are excluded from automatic updates.

## Diagnostics

Plugin Center reports lifecycle state, process id, load time, call count,
latency, process memory, process CPU usage, failures, crashes, restarts,
warnings, logs, contribution counts, dependency state, and a bounded
performance score. Portable per-plugin GPU accounting is reported honestly as
unavailable. The global diagnostics snapshot includes plugin and marketplace
health alongside tools, renderers, workers, and desktop services.

Plugins marked `"lazy": true` register lightweight proxies at startup and do
not launch a process until their first command, tool, renderer, model, or
automation call. Inactive lazy plugins are unloaded in the background and
remain available for on-demand restart.

## Testing

The Phase 6 suite verifies:

- manifest and semantic-version validation
- permission review and denied I/O
- process isolation, crashes, and timeouts
- tools and renderers registering and unregistering cleanly
- dependency ordering, conflicts, and cycles
- safe install, path traversal rejection, update, pin, and rollback
- hot reload and persistent storage
- local marketplace search and CLI packaging
- discovery and dependency sorting with 100 plugins

Use:

```powershell
python -m unittest tests.test_plugin_platform -v
```
