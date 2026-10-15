# MORICE Phase 2 report

Implemented locally in `E:\MORICE`. All changes remain local. No commit, push,
merge, tag, release, upload, deployment, publication or public website change was
performed. The checkout contains other user edits and staged files; those were
preserved. This report describes the Phase 2 additions, not all changes in the checkout.

## Validation evidence

| Check | Final result | Local evidence |
| --- | --- | --- |
| Phase 1 kernel/runtime foundation | 50 passed | `build/phase2-foundation-tests.log` |
| New Phase 2 tests | 41 passed | `build/phase2-agent-tests.log` |
| Kernel, agents, runtime and existing orchestration | 113 passed in 18.76 s | `build/phase2-targeted-tests.log` |
| Complete regression suite | **643 passed, 59 subtests passed in 103.98 s** | `build/phase2-full-tests.log` |
| Actual offscreen Qt startup/chat workflow | 5 tasks completed, 2 peak workers, zero critical startup failures | `build/phase2-startup-smoke.log` |
| Activity dialog | 5 role/task rows; expandable evidence; optional broken capability isolated | Same startup log |
| Local wheel | Build succeeded; all 9 agent and 14 kernel modules byte-matched current source | `build/phase2-packaging.log`, `build/phase2-package/` |
| Source checks | Compileall and `git diff --check` passed | Local command output |

The suite grew during this session because the shared checkout also received
other user changes. Counts are the observed final collection, not an assumption
that every newly collected test was authored for Phase 2.

## Controlled performance evidence

Medians of three runs per mode, with identical workflow behavior and concrete
outputs. The final benchmark ran after the full suite and UI smoke finished.

| Workflow | Sequential | Parallel | Speedup | Peak workers |
| --- | ---: | ---: | ---: | ---: |
| Three independent controlled I/O tasks, 150 ms each | 472.80 ms | 164.16 ms | **2.88×** | 3 |
| Two candidate patches, real Python tests, independent artifact verification | 727.26 ms | 392.07 ms | **1.85×** | 2 |
| Three small actual document previews, comparison, independent readback | 27.94 ms | 29.46 ms | **0.95×** | 3 |

The coding test fixtures intentionally include a 150 ms wait before two actual
assertions. This demonstrates useful overlap for independent waiting/test work;
it does not establish speedup for arbitrary production builds or CPU-bound Python.
The document result shows that parallelism can cost more than it saves on small work.

The direct Calculator route/execution/verification fixture median was **0.387 ms**
over 250 samples. It entered zero agent workflows. This excludes actual OS launch,
GUI rendering and model latency. The Phase 1 fixture previously measured about
0.214 ms; the absolute difference is small but is not described as zero overhead.

Benchmark-process peak sampled RAM was **93.52 MiB**; CPU process time was
**1.140625 s** over **5.783551 s** wall time, averaging **19.72% of one core**.
This RAM measurement excludes separate test subprocesses. The end-of-run host GPU
sample was 46% utilization and 309 MiB VRAM used. These are host end samples, not
peak agent usage and not attributable to inference: **no model was loaded**.
No parallel LLM speedup or inference VRAM peak is claimed.

Raw measurements and scope notes are in `build/phase2-benchmark.json`.

## Requested delivery details

1. **Phase 1 foundation status:** Verified executable contracts, adapters, scheduler,
   context, permissions, resource leases, events, results and verification with
   source inspection and the existing tests. See the foundation audit.
2. **Phase 1 fixes:** Preserve failed tool output, deduplicate evidence, lock graph
   snapshots, reject task additions while running, expose resource descriptors,
   record attempts and publish actual resource wait/resume events.
3. **Runtime architecture:** One coordinator over the existing TaskGraph, scheduler,
   kernel and event bus; functional workers exchange versioned structured results.
4. **Coordinator design:** Validates/admit/schedules graphs, captures results,
   handles cancellation, reports failures/conflicts and persists checkpoints.
5. **WorkerManager design:** Explicit lifecycle records, scoped cancellation,
   compact context, role/schema checks, kernel execution and result collection.
6. **Agent role model:** Typed role IDs, descriptions, allowed/preferred capabilities,
   permissions, model requirements, resource profiles, context and result policies.
7. **Initial role set:** Coordinator, Researcher, Coder, Tester, Analyst, Verifier,
   Web Researcher, Vision Analyst and Simulation Worker; nine roles.
8. **Task decomposition:** Concrete document comparison and candidate coding
   builders produce validated graphs; supported chat routing invokes these plans.
   Unsupported goals retain the existing path instead of a fabricated plan.
9. **Parallel scheduling:** Dependency-ready copies execute in a shared bounded
   pool; collection commits shared state before descendants can start.
10. **Worker concurrency limits:** Default four active workers across workflows,
    two admitted workflows, 32 tasks, depth eight, two attempts, 300 s runtime.
11. **Resource-aware execution:** Existing kernel leases enforce CPU/IO/GPU/model,
    VRAM and exclusive foreground constraints. Invalid claims fail validation.
12. **GPU/VRAM strategy:** RTX 3050 6 GB evidence informed conservative defaults;
    one model request reserves the GPU and configured local VRAM budget.
13. **Shared model behavior:** Existing ModelRouter is reused; explicitly configured
    callbacks share an already-owned backend. No worker creates a model instance.
14. **Context packet design:** Selected goal/task/project/files and declared upstream
    results only, with byte budgeting, truncation, provenance and data boundaries.
15. **Shared state model:** Workflow/task/worker namespaces; JSON copies; bounded
    version history. No shared generic `result` key or full transcript replication.
16. **Agent result contract:** Role/task/worker IDs, explicit state, summary, structured
    output, evidence/artifacts, errors/warnings, metrics, verification and retryability.
17. **Verification model:** Separate Verifier tasks inspect actual test exit codes,
    generated content and independently read document previews through the kernel.
18. **Conflict resolution:** Contradictory structured claims stay unresolved or fail
    verification; final output does not silently choose a successful-looking worker.
19. **Failure propagation:** Unrelated branches continue; required descendants block;
    optional branch failures retain warnings through existing dependency policies.
20. **Cancellation behavior:** Linked tokens stop new scheduling and active work;
    branch cancellation is supported; partial completed results survive.
21. **Timeout behavior:** Worker and workflow deadlines use the existing kernel;
    Tester processes use existing process-tree termination and reaping.
22. **Retry behavior:** Existing bounded RetryPolicy; permission failure does not
    trigger blind retries; fallback capabilities must also satisfy the role.
23. **File-write conflict handling:** Existing exclusive DISK lease and atomic patch
    authority; mandatory preview existence/hash baselines reject stale writes.
24. **Checkpoint/resume support:** Atomic graph/results/version/fingerprint JSON;
    pending tasks resume, completed tasks are retained, uncertain mutations block.
    Source/artifact/input changes invalidate affected descendants.
25. **Progress/status UI:** Main-thread timer shows real counts; status queries work
    during activity; small role/task dialog expands evidence/errors/timings.
26. **Telemetry:** Planning, queue, resource wait, execution, verification, retries,
    failures, peak workers, model reservations/usage and overall wall time.
27. **Sequential benchmark results:** 472.80 ms controlled I/O; 727.26 ms coding;
    27.94 ms documents, using the same results and checks as parallel runs.
28. **Parallel benchmark results:** 164.16 ms I/O; 392.07 ms coding; 29.46 ms documents.
29. **Measured speedup:** 2.88× controlled I/O; 1.85× coding fixture; documents 0.95×.
    The small document case regresses slightly and is reported explicitly.
30. **Peak worker count:** Three in controlled I/O/documents and two in coding;
    tests enforce three workers over ten tasks and across concurrent workflows.
31. **CPU/RAM observations:** Final benchmark process used 93.52 MiB sampled peak
    RAM and averaged 19.72% of one core. Windows profiler handle typing was corrected.
32. **GPU observations:** Hardware has 6144 MiB VRAM. Final host end sample was
    46% utilization/309 MiB used; not an inference or peak benchmark measurement.
33. **Representative coding workflow:** Real square-function candidates are written
    in separate temporary roots, tested by Python processes, independently read
    back and reported. A deliberately failed candidate preserves AssertionError
    logs and makes verification/final output fail.
34. **Representative non-coding workflow:** Three local sources are read concurrently,
    compared as structured evidence and independently read again. Contradictory
    JSON claims and source injection cases cannot become verified instructions.
35. **Tests added:** 41 Phase 2 cases, including parametrized resource and validation
    cases; real document/coding workflows, subprocess cancellation, stale artifact
    recovery, model fallback/budgets, observer lock ordering and permission constraints.
36. **Targeted tests run:** Final kernel/agent/runtime/orchestration selection:
    113 passed in 18.76 s. New agent selection: 41 passed in 3.71 s before the final
    result-formatting update; all 41 are also included in the final targeted/full runs.
37. **Full regression suite:** 643 tests and 59 subtests passed in 103.98 s on the
    final implementation, covering existing MORICE functionality.
38. **Startup smoke:** Actual RuntimeServices.start, MoriceWindow, on_send,
    worker-to-Qt result delivery and activity expansion succeeded. An intentionally
    broken optional capability was isolated; zero critical health failures.
39. **Performance regressions:** Small document work has slight parallel overhead;
    direct action fixture is still sub-millisecond but higher than the prior fixture.
    New pools are lazy; ordinary PC routing precedes agent planning. Resource waits
    occupy worker slots and can cause conservative queueing under contention.
40. **Known limitations:** Open-ended planning/code generation requires a configured
    planner/backend integration. Reasoning is honestly unavailable by default;
    remote callbacks currently share the conservative GPU queue. Web integration
    is existing search snippets, not full navigation/citation verification. Vision
    adapter provides metadata, not OCR/semantic analysis. File previews are bounded,
    not full-file verification for arbitrarily large files. Checkpoint resume is an
    explicit API. Uncooperative threads retain leases until they exit.
41. **Files added:** Nine modules in `morice/agent_runtime/`; this report,
    `parallel-agent-runtime.md`, `parallel-agent-runtime-audit.md`;
    `tests/test_parallel_agents.py`; `scripts/benchmark_parallel_agents.py`.
42. **Files modified in Phase 2:** `morice/agent_orchestrator.py`,
    `morice/runtime_services.py`, `morice/pyside_app.py`, and kernel
    `adapters.py`, `events.py`, `execution.py`, `resources.py`, `scheduler.py`,
    `tasks.py`. Existing user changes elsewhere were not attributed to this phase.
43. **Readiness for Phase 3:** Shared cancellation, events, evidence, verification,
    resource waits and failure contracts support stronger observe/recover loops
    without rebuilding PC/browser automation now.
44. **Readiness for Phase 4:** Concrete Coder/Tester/Verifier workflow and artifact
    contracts are demonstrated. Autonomous large-project planning, repair loops
    and isolated parallel coding workspaces remain Phase 4 work.
45. **Readiness for Phase 5:** Resource claims and capabilities retain node IDs;
    graph/results/context are serializable. No new device networking was implemented.
46. **Readiness for Phase 6:** Researcher, Analyst, Simulation and Verifier roles can
    drive registered existing simulations and numerical tools. No new laboratory
    or scientific simulator ecosystem was built.

## Review and use

See `parallel-agent-runtime.md` for the architecture diagram, minimal API examples,
role registration, model callback contract, UI commands and checkpoint behavior.
See `parallel-agent-runtime-audit.md` for foundation evidence and the fresh audit.

The local wheel is `build/phase2-package/morice_ai-0.8.0-py3-none-any.whl`.
It is a source wheel validation artifact, not a claim that a new portable Windows
executable was built or released. The supplied implementation is ready for local review.
