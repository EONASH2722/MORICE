# MORICE Phase 1 implementation and validation report

Working repository: `E:\MORICE`. Date: 2026-10-03. The configured `D:\MORICE` path did not exist, so the repository explicitly specified in the request was used. Existing working-tree edits were preserved; no commit, push, merge, tag, release, upload or deployment was performed.

Final validation status: **passed**. Full Python suite: **601 passed, 59 subtests passed in 84.14 seconds**. All 36 new kernel tests are included. Offscreen Qt startup, startup health, local wheel build, exact wheel/source comparison, Python compilation and whitespace checks passed.

## Requested completion report

| # | Topic | Delivered result |
| --- | --- | --- |
| 1 | Existing execution architecture | Launcher -> `MoriceWindow` -> `RuntimeServices`. Deterministic PC requests use `FastActionRouter` and `ControlProviderRegistry`; project UI directly calls `AgentToolExecutor`; visualization has a separate renderer scheduler/cache. Existing goal/device orchestration remains a compatibility path. |
| 2 | Reusable systems | Existing tool definitions/schema validation, scoped tool grants, PC broker/providers/verifiers, atomic patch/undo, WorkingMemory, interactive/background pools, ActionHistory, PerformanceProfiler, structured logs and Qt signals. |
| 3 | Architectural problems | Different task/result/state formats; no shared resource leases or cancellable dependency graph; automatic verification of plain legacy return values; timeout detachment without resource ownership; Windows launcher cancellation could leave descendants. Four baseline assertions were stale and a hover test depended on persisted ambient events. |
| 4 | Kernel architecture | Modular `morice/kernel/`, owned by runtime services. Registry -> context -> authorization -> node-scoped leases -> execution -> verification -> final state/events/history. Model and Qt independent. |
| 5 | Files added | 14 modules listed below; architecture audit, developer guide, this report, benchmark script and 36 kernel tests. |
| 6 | Files modified | `agent_tools.py`, `pc_control.py`, `runtime_services.py`, `unified_intelligence.py`; five existing test files aligned with the already-present UI/personalization behavior and deterministic pet fixture. Existing unrelated edits were retained. |
| 7 | Capability contract | Stable ID/name/version/provider/category; input/output schemas; permissions/risk; platform/resource/node requirements; background/streaming/cancellation/verification/retry flags; dependencies; estimated cost/latency; availability and timeout. |
| 8 | Registry | Register/unregister/lookup/search; metadata, platform, permission, resource, availability and health filters. Cached lightweight lazy health and explicit refresh. Optional health failures are isolated. |
| 9 | TaskGraph | Validated DAG, stable IDs, atomic ready-node claims, priority order, dependency policies (`SUCCESS`, `COMPLETED`, `FAILURE`), optional branches, explicit unavailable skips and safe JSON checkpoints. |
| 10 | Task states | Pending, ready, running, waiting, blocked, verifying, succeeded, failed, cancelled, skipped and retrying enums. Runtime snapshots and compatibility metadata expose minimal public status. |
| 11 | Execution result | Status/success, output, observations, artifacts, warnings, typed errors, metrics, evidence, retryability, verification requirement/result, task/capability/attempt IDs. Legacy objects stay in-process and are excluded from serialization. |
| 12 | Verification | Verified/failed/inconclusive/not-applicable plus evidence. Failed or inconclusive verification overrides apparent success; required verification cannot pass as not applicable. Final tool history records the verified kernel outcome. |
| 13 | ContextResolver | Reuses runtime WorkingMemory and desktop/project context; captures structured task context without transcripts. Explicit reference constraints resolve task inputs, and ambiguous/unknown action targets request clarification before execution. |
| 14 | Permission model | One kernel facade reuses PermissionController for native providers and existing tool/PC authorities for migrated operations. Domain grants are previewed, then consumed exactly once by original execution. Extra task permission requirements cannot be overridden by an adapter grant. |
| 15 | Risk model | Existing low/medium/high enum extended with critical. Exact approval for high/critical operations; metadata informs allowed paths and logging. Existing path/sandbox restrictions remain authoritative. |
| 16 | EventBus | Typed IDs/timestamps/source/task/project/payload/severity; ordered subscribe/unsubscribe/publish; duplicate suppression, weak Python bound methods, explicit function cleanup, exception isolation and bounded reentrant storms. |
| 17 | Scheduler | Sequential graph driver on existing reserved interactive/background pools, with priority within graphs and atomic claims for future workers. Queued cancellation finalizes pending states. No agent swarm or global preemption is added. |
| 18 | Resources | Atomic all-or-none capacity/exclusive leases, aggregate budget checks and node IDs. Runtime declares disk and foreground UI. Opening applications and screenshots reserve foreground UI; synthetic remote GPU contention is tested. |
| 19 | Cancellation | Linked graph/task/attempt/child tokens; interruptible waits/backoff; scheduler and kernel cancellation; terminal process-tree/group termination and reaping. Detached work retains leases until exit and cannot replace final task state. |
| 20 | Timeout/retry | Task deadline spans attempts and backoff; bounded 1..10 attempts, allowed error codes, explicit fallback IDs, independent authorization. Only retryable outcomes from retry-supporting capabilities are retried. Atomic mutation adapters finish before reporting a late deadline. |
| 21 | Telemetry | Bounded queued/started/selection/queue/resource/execution/progress/verification/completion timing records; first progress is the first progress record per attempt. Existing profiler/log integration correlates public task/capability/attempt IDs. No private model reasoning. |
| 22 | Existing capabilities migrated | Eight built-in tools, five PC actions, and three native adapters reusing existing file preview, guarded calculation and graph rendering. One deterministic echo fixture. See IDs below. |
| 23 | Fast path | Existing `Open Calculator` routing remains deterministic with zero model invocations; registered PC execution now passes through authorization, leases and verification without planner/model work. |
| 24 | Performance | Median added Calculator fixture dispatch cost 0.153 ms; echo 0.078 ms; event with one subscriber 0.0033 ms; kernel constructor/registration 0.310 ms in real runtime initialization. Isolated fresh-process kernel import 88.45 ms. See measurement limits below. |
| 25 | Tests added | 36 tests covering registry/health/filtering, DAG/conditions/optional failures, verifier rejection, permissions/exact grants, cancellation/descendants, deadlines/retries, resources, priority/admission, queued cancellation, safe checkpointing, reference ambiguity, native adapters, compatibility history and startup isolation. |
| 26 | Targeted results | Final affected-subsystem run: 101 passed, 14 subtests passed in 12.02 seconds. This includes kernel tests plus agent, PC, runtime and unified-intelligence suites. |
| 27 | Full regression | 601 tests and 59 subtests passed in 84.14 seconds on the final source. No failures or unexplained regressions remain in the full suite. |
| 28 | Startup | Actual offscreen Qt `MoriceWindow` opened using a started RuntimeServices instance with an optional provider throwing ImportError. Provider became unavailable; echo still executed; 18 registrations including the fixture; zero critical startup health failures. |
| 29 | Known limitations | In-process Python cannot be force-killed; inline native/atomic operations rely on existing bounded implementations. Schema validation is the existing supported subset. Graph nodes run sequentially in Phase 1. Cross-graph preemption, automatic checkpoint persistence, remote dispatch, and full migration remain future work. Real Calculator launch/hardware/model latency is excluded from the benchmark. |
| 30 | Migration map | The developer guide maps remaining PC/browser/media, Project Builder plans, visualization jobs, model/vision/voice, research, trusted device/node providers, plugins/web/integrations and specialized goal orchestration into these contracts. |
| 31 | Phase 2 readiness | Multiple workers can atomically claim independent nodes, call `run_task`, and publish results through `finish`; shared state, leases, cancellation and verification already support that execution model. Phase 2 can build the worker-agent pool on these contracts without replacing the Phase 1 core. Actual agent orchestration is not implemented here. |

## Files and integration boundaries

Added kernel modules:

`__init__.py`, `contracts.py`, `schema.py`, `registry.py`, `tasks.py`, `scheduler.py`, `execution.py`, `context.py`, `permissions.py`, `cancellation.py`, `events.py`, `resources.py`, `telemetry.py`, `adapters.py`.

`agent_tools.py` now delegates registered tool IDs to the kernel, preserving all other tools on their original executor. Schema validation moved intact into the shared module. Scoped-grant preview does not consume approval. Terminal cancellation/deadlines kill owned descendants, including Windows virtual-environment launcher children. Completion callbacks record final verification outcomes in the existing action history.

`pc_control.py` adds non-consuming permission previews and delegates only registered PC IDs. Its original provider selection, native execution, desktop context, process observation and result types remain the underlying implementation. No Qt widgets are accessed from kernel workers.

`runtime_services.py` initializes and registers the kernel, shares existing permissions/memory/worker pools/profiler/logs, exposes bounded task history in runtime snapshots and cancels the kernel during shutdown. `unified_intelligence.py` adds the critical risk level while retaining its existing APIs.

Registered migrated IDs:

- Tools: `filesystem.search`, `filesystem.preview_patch`, `filesystem.apply_patch`, `project.index`, `project.verify`, `terminal.run`, `git.status`, `git.diff`.
- PC: `application.open`, `system.status`, `file.open`, `file.search`, `screenshot.capture`.
- Native adapters: `filesystem.read`, `python.calculate`, `graph.render`.
- Deterministic fixture: `kernel.echo`.

Existing UI tool and selected PC calls now pass through the shared kernel automatically. Native calculation, graph and preview adapters are available through the kernel API; the existing visualization UI's scheduler/cache is intentionally retained for gradual migration.

## Baseline and regression accounting

Before kernel changes, the initial full run reported 5 failures, 551 passes and 59 subtests in 148.35 seconds. The failure evidence is retained in `build/phase1-baseline-tests.log`:

- Conversation/workspace tests expected old unescaped address wording; assertions now verify the existing JSON-quoted identity data and instruction boundary.
- Premium/visualization compact-composer tests expected controls that the already-modified UI moved into the quick-actions menu; assertions now verify compact menu visibility and expanded labels at 1100 px.
- Hover animation was interrupted by persisted ambient pet events; that isolated motion test now explicitly disables special events. Pet event behavior retains its own dedicated tests.

These updates preserve the user's existing product changes. Additional tests already present/being updated in this active checkout account for collection growth beyond the initial run; this report attributes only the 36 new kernel tests to this phase.

## Performance and packaging evidence

The deterministic benchmark uses a verified application fixture and the real fast router/permission broker, comparing direct legacy execution with kernel dispatch. It uses 250 samples per command and 1000 event samples. It excludes real OS launch, model inference and disk logging, and therefore measures routing/kernel overhead rather than complete user-visible latency. Runtime initialization measured 145.56 ms in that run; the instrumented constructor/registration contribution was 0.310 ms. Fresh-process import is an isolated upper-bound-style measurement that also loads standard-library dependencies already used elsewhere by the application.

Results are reproducible with `python scripts/benchmark_capability_kernel.py`; machine timing naturally varies. Latest JSON: `build/phase1-benchmark.json`.

Local packaging command: `python -m build --wheel --no-isolation --outdir build/phase1-package`. The environment initially lacked the `wheel` build dependency; it was installed locally into `.venv` from the available cache. The subsequent build succeeded, and archive inspection confirmed all 14 kernel modules. Local output: `build/phase1-package/morice_ai-0.8.0-py3-none-any.whl`. No release binary build, publication or upload was performed.

Validation logs: `build/phase1-affected-tests.log`, `build/phase1-full-tests.log`, `build/phase1-startup-smoke.log`, `build/phase1-packaging.log`. Python compilation and `git diff --check` passed. Existing deleted documentation screenshots were preserved; they are unrelated to runtime assets or this phase.

See [architecture audit](capability-kernel-audit.md) and [developer guide / migration map](capability-kernel.md).

## Final independent review

Reviewed the implementation boundaries, callback lifetime, provider failure isolation, worker admission, grant consumption, actual process cleanup and late completion behavior. Corrections made during review include aggregate resource budgets, graph/task ID separation, queued cancellation state, whole-task retry deadlines, sub-poll-interval timeout enforcement, screenshot ID alignment, extra task permission enforcement, explicit target clarification, verified final action history and suppression of progress after terminal state. Tests exercise these cases; final wheel contents exactly match all 14 source modules.
