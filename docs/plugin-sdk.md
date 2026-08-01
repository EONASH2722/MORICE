# Plugin SDK

MORICE plugins extend the desktop platform without importing private UI internals. Packages are
validated before installation and run in a separate bounded host process.

## Contributions

A plugin may contribute namespaced models, tools, deterministic renderers, commands, themes,
workspaces, settings, memory providers, voice providers, or automations. The manifest declares the
plugin ID, version, compatible MORICE version, entry point, permissions, and contributions.

## Rules

- Use globally unique, namespaced contribution IDs.
- Request only the permissions required by the feature.
- Keep renderer output typed, deterministic, and validated.
- Never claim success before the host receives a verified result.
- Do not read private runtime data or project folders without the declared permission.
- Treat network, subprocess, filesystem, desktop, and secret access as separate capabilities.

## Developer Workflow

```powershell
python -m morice.plugin_cli validate path\to\plugin
python -m unittest tests.test_plugin_platform -v
```

Plugin Center can inspect manifests, review permissions, install local or verified HTTPS packages,
pause, reload, update, roll back, and remove plugins. A plugin crash or timeout removes its active
contributions without terminating MORICE.
