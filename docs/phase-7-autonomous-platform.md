# MORICE Phase 7 Autonomous Platform

Phase 7 connects MORICE's agent, project, desktop, rendering, plugin, memory,
recovery, packaging, and diagnostics systems through one production-facing
platform layer. It does not give model prose authority over the computer.
Models propose work; typed services perform and verify it.

## Request Flow

```text
request
  -> unified orchestrator
  -> intent + context + relevant knowledge
  -> specialist work items
  -> tool / renderer / plugin selection
  -> exact permission check
  -> execution
  -> verification
  -> project dashboard + conversation result
  -> bounded knowledge update
```

The orchestrator delegates structured work to coding, research, planning,
documentation, debugging, testing, visualization, simulation, desktop, file,
and voice roles. These are responsibility boundaries over one trusted runtime,
not independent processes that can bypass MORICE permissions.

## Autonomous Project Work

`ProjectWorkflowEngine` creates a resumable feature workflow:

1. Analyze project context.
2. Generate a multi-file preview.
3. Apply an explicitly approved patch.
4. Run the detected build.
5. Run focused and project tests.
6. Diagnose and retry verified failures.
7. Apply approved documentation changes.
8. Store verified project knowledge.

Apply and documentation stages start in `waiting_approval`. Approval is exact,
one use, and bound to one workflow stage. Existing file patching retains its
atomic writes, stale-preview refusal, rollback, and protected undo behavior.

## Project Dashboard

The Tools workspace now has a permanent `Platform` page. When Project Mode has
a work folder, it displays:

- languages, frameworks, build systems, entry points, assets, and dependencies;
- current autonomous runs and progress;
- Git branch, dirty state, commits, tags, conflicts, and timeline;
- TODO/FIXME/HACK/BUG issues with source locations;
- open files, build state, renderer state, tests, and performance;
- bounded relevant project knowledge.

Project indexing excludes dependency, build, VCS, cache, and MORICE state
folders. Dashboard refreshes reuse a short cache so repeated UI refreshes do
not scan thousands of files continuously.

## Knowledge Graph

The local SQLite graph stores typed nodes for projects, notes, research,
conversations, documents, code, symbols, plugins, preferences, visualizations,
and simulations. Edges describe relationships such as `contains`, `declares`,
and `references`.

Retrieval is deterministic and project aware. Only overlapping relevant nodes
are passed to the request context. Results are bounded, secrets are redacted
before storage, and the graph can be exported as JSON. Project indexing stores
file metadata and symbols rather than complete source bodies.

## Git Contract

Read-only status, diff, history, branch, tag, conflict, and timeline inspection
need no approval. Repository creation, clone, branch creation, merge, commit,
tag, revert, conflict resolution, and local release creation require a
matching, expiring, one-use approval.

Commits require explicit relative paths. Revert requires an exact commit hash.
Conflict paths are contained inside the repository. Local release creation
produces an annotated tag and a verified local manifest; MORICE does not claim
that a remote release was published without a configured provider.

## Secure Storage, Backup, and Export

On Windows, secrets and encrypted backups use the current user's DPAPI
credentials. There is no plaintext fallback. Backups and exports:

- reject traversal and symbolic-link payloads;
- enforce file-count and byte limits;
- verify SHA-256 values during restore;
- skip known secret files and text that looks like a credential;
- use temporary files plus atomic replacement.

Exports can bundle selected projects, conversations, memory, visualizations,
settings, logs, diagnostics, and platform state. The UI's Platform export
action uses this same bounded exporter.

## Updates and Recovery

Stable and beta update channels share one verified staging service. A package
must have a valid manifest, exact byte count when supplied, and matching
SHA-256 checksum. Installation scheduling requires exact approval.

On restart, the packaged launcher hands the update to a separate updater
process. Portable ZIP updates are extracted into a contained staging folder,
copied atomically, and backed up per changed file. A failed copy restores the
previous files. Installer EXEs launch silently after checksum validation.
Unsupported package types fail honestly.

Crash reports, session snapshots, safe recovery, plugin process isolation, and
renderer failure isolation remain owned by their existing runtime services.

## First Run and Packaging

The first packaged launch opens a five-step wizard:

- local/offline behavior;
- detected GPU, VRAM, RAM, disk, and model class;
- optional components;
- permission behavior;
- first workspace location.

`installer/MORICE.iss` defines a per-user x64 Inno Setup package with shortcuts,
upgrade/repair support, and safe built-in uninstall. `scripts/build-release.ps1`
runs Python and VNext tests, builds PyInstaller, optionally creates portable
and installer artifacts, and emits SHA-256 checksums.

The bundled model pushes the offline installer beyond Windows' single Setup
executable limit. Inno Setup therefore emits one Setup executable and numbered
data slices; keep every generated Setup file together when installing. The
portable Zip64 archive remains a single-file distribution option.

## Public API Surface

Primary integration classes:

```python
from morice.platform_services import PlatformServices
from morice.autonomous_platform import (
    KnowledgeGraphStore,
    MultiAgentCoordinator,
    ProjectDashboardService,
    ProjectWorkflowEngine,
    UnifiedPlatformOrchestrator,
)
```

Plugins continue to use the public Plugin SDK. They cannot import authority
from Phase 7; plugin permissions and process isolation are unchanged.

## Honest Limits

- Cloud sync is optional infrastructure and is not active without a configured
  provider. Local encrypted backup remains available.
- Remote Git releases are not reported as published unless a provider performs
  and verifies that operation.
- Model recommendations are hardware-fit estimates, not benchmark guarantees.
- An unavailable renderer, tool, updater, installer compiler, or secure-storage
  backend is reported as unavailable rather than simulated.
