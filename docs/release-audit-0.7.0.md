# MORICE 0.7.0 Release Audit

Audit date: 2026-08-02

## Existing GitHub Releases

| Tag | Finding | Required action |
| --- | --- | --- |
| `morice-pc-app` | Legacy May 2026 PC archive, four assets, zero downloads, replaced by the 0.7.0 installer and portable lanes | Remove after the 0.7.0 release is published and verified |
| `model-hermes-3-llama-3.1-8b-q4-k-m` | Obsolete Hermes model; the remote release is incomplete because `part002` is missing | Remove the release and tag |
| `v1.2` | Tag exists without a GitHub Release and does not match current application version metadata | Review and remove if it is not intentionally retained as source history |

No existing release is a valid substitute for MORICE 0.7.0. Historical assets must not be
renamed or reused because they were built from different source and model revisions.

## Current Release Boundary

- Application, executable, installer, portable archive, wheel, sdist, changelog, release notes,
  and expected tag use version `0.7.0` / `v0.7.0`.
- The installer and portable lanes intentionally bundle Qwen2.5 Coder 7B Q4.
- The Python package intentionally excludes all local models and llama runtime executables.
- A lone `MORICE.exe` is not advertised as standalone because the PyInstaller one-folder build
  requires `_internal` and application assets.
- Code signing is unavailable; no fake signature is generated.

## Publication Gate

Publish only from the exact verified commit after it reaches the default branch. Before making the
release public, verify checksums, package-content report, installer install/uninstall, portable
launch, shortcuts, taskbar icon, wheel installation, and the GitHub Actions release-validation run.

The old remote releases require repository-admin deletion. This checkout can push Git data, but no
authenticated GitHub release-management endpoint is available to this build session.
