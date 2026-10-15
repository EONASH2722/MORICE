# Phase 4 delivery report — Project Builder 2.0

Date: 2026-10-04. Repository: `E:\MORICE`. Phase 4 is implemented and validated for the controlled project contracts described below. General platform/provider constraints are explicit; unavailable critical checks never become verified.

Final verification: **735 tests and 59 subtests passed in 217.47 seconds**. The final builder/browser/Project Mode selection passed **46 tests in 118.49 seconds**. Startup has no critical failures. The local wheel contains all 42 kernel/agent/action/project modules with byte-for-byte agreement with source and valid archive integrity. All work remains local and uncommitted.

1. **Phase 1 status.** Live CapabilityKernel, registry/health/schema, TaskGraph, typed execution/verification, centralized permissions/risk, resources, events, cancellation, timeout and telemetry were inspected and exercised. Foundation selection: 148 tests/eight subtests in 26.21 seconds; final full regression remains green.

2. **Phase 2 status.** Existing AgentCoordinator, bounded WorkerManager, roles, compact context, SharedTaskState, verification workers, resource admission and checkpoints remain the implementation path. There is no replacement agent runtime. Shared model budgets now survive multiple project graphs.

3. **Phase 3 status.** Existing desired-state bindings, independent observations, action journal, verification, recovery and permission handling remain authoritative. Shared process lifecycle and rendered browser inspection extend these contracts. Full semantic vision and universal desktop UIA remain provider constraints, not fabricated completion claims.

4. **Prerequisite repairs.** The foundation tests passed before project work. Necessary extensions add owned background process lifecycle and actual rendered layout/screenshot/console observations, retain project session metadata through workers and admit one bounded shared ModelBudget across graphs. No core executor/scheduler/authority was replaced.

5. **Existing Project Mode.** Existing request/manifest analysis, incremental index, workflow adapters, atomic preview/apply/undo, legacy builder, command panel and launch plans were reused. Legacy file/command success is retained as compatibility data, with a separate authoritative full-project result.

6. **Architecture.** Domain sessions plan requirements, architecture and owned scopes; existing TaskGraphs implement/check/integrate; real commands resolve/build/test/run; Phase 3 observations check output; bounded repairs rerun validation; final requirements, artifacts and source hashes determine status. See the diagram and API in `project-builder-2.md`.

7. **Added modules/files.** Eight modules under `morice/project_build/`: `__init__.py`, `contracts.py`, `workspace.py`, `discovery.py`, `planning.py`, `localtools.py`, `proposals.py`, `runtime.py`. Shared Phase 3 additions: `action_runtime/processes.py` and `inspection.py`. Scripts: `demo_project_builder.py`, `benchmark_project_builder.py`, `verify_builder_startup.py`. Tests: `test_project_build_runtime.py`, `test_project_build_browser.py`. Three Phase 4 documentation files and local `build/phase4-*` evidence artifacts.

8. **Changed files.** Existing `autonomous_builder.py`, `runtime_services.py`, `pyside_app.py`, `project_index.py`, `action_runtime/qt_browser.py`, `agent_runtime/coordinator.py`, `workers.py`, `roles.py`, `MORICE.spec`, and GUI compatibility tests in `test_visualization.py`. These files also contain earlier authorized phase changes; unrelated user edits/deleted screenshots were preserved and are not attributed to Phase 4.

9. **Requirements.** Requirements retain identity, text, category, origin, observable check, status and evidence. Unsupported/unknown checks remain `not_verified`; optional suggestions cannot silently become required features. GUI proposals do not import model assertions as accepted requirements.

10. **Architecture planning.** Existing request/manifest conventions determine language/framework/project type; minimal modules, storage/testing assumptions and owned scopes are recorded. Known scaffolds remain small; unavailable generation or complex semantics produce explicit partial planning/results.

11. **TaskGraph planning.** Independent Coder patches each precede their Tester source check. A single root integration patch follows successful actual staging readback. Verification/command/browser graphs use existing typed tasks and role allowlists; hash tasks are batched within existing subtask limits.

12. **Type detection.** Existing index and adapters recognize Python, static web, Node, .NET, Java, Rust, Go, Android and game/editor projects from real files/manifests/tool availability. Detection does not imply execution certification.

13. **Actually validated types.** Python addition CLI, local Python environment preparation, local Python HTTP API and a responsive static HTML/CSS/JavaScript application in actual Qt Chromium. Native/mobile/game-editor/database workflows were not validated end to end.

14. **Fingerprinting.** Bounded indexing captures languages, frameworks, manifests/package managers, dependencies, entry points, file count/truncation, discovered workflow and read-only Git state. Generated builder caches are excluded from normal indexing.

15. **Coding workers.** Existing Coder applies approved staged patches; Tester executes real source and integration checks; Verifier reads actual files/artifacts; Browser operates actual Chromium. Shared configured model proposals/repairs use `agent.reason`, its existing router and budget; workers do not construct/load private models.

16. **File ownership.** Exactly one explicit glob owner or default domain owner per changed file. Overlap, unsafe identifiers and duplicate Windows staging identities are refused. Tests and central configuration have their own scopes.

17. **Isolated workspaces.** Bounded private copies under `.morice-build/<session>/workspaces/<owner>` preserve source context while excluding generated/secret/symlink data. Only owned paths are patched. Cleanup targets the resolved owned scope; no Git stash/reset/checkout is needed.

18. **Stale baseline protection.** Staging hashes are separate from reviewed root hashes. Integration uses existing atomic baseline checks. Staged output and final source hashes are independently read back; late user edits prevent repair and completion. Redirected cache/secret/device/ambiguous paths are rejected.

19. **Dependencies.** Actual declaration/environment checks are run. Simple Python requirements prepare/use a project `.venv` and execute pip, with URLs/VCS/options refused; the local-environment fixture performs real environment creation and an empty explicit requirements install. Missing dependency/tool execution remains a failure/unavailable result, with no claim that arbitrary third-party resolution was proven. Existing manifest/lockfile managers are reused.

20. **Build discovery.** Real static/Python package helpers or existing framework commands/scripts are selected. Build output is kept under `dist`/owned cache, separate from source. The Python/static build creates a genuine source archive, not a native executable.

21. **Test discovery.** Actual unittest/pytest or manifest/framework test commands are selected. Missing tests cannot pass DefinitionOfDone; zero-test runner output fails. Acceptance tests cannot be removed/replaced just to green a repair.

22. **Run discovery.** Actual Python entry points, static build output, declared local services or installed workflow run commands are used. A missing observable runtime contract remains unavailable, even if a command or editor was detected.

23. **Build verification.** Real subprocess exit/output, source checks and actual built archive content are recorded. A passing no-op command cannot certify stale/missing archive sources.

24. **Test verification.** Actual failing Python assertions were preserved in diagnostics, repaired in implementation source and rerun successfully. No test weakening, skipped required test or hardcoded command success was used.

25. **Runtime verification.** CLI exit/output and owned process/local HTTP readiness are observed. The API fixture compares an actual JSON response. Application startup is separate from application behavior; failed cleanup also prevents verified health.

26. **Visual inspection.** Actual PNG bytes and actual DOM geometry/text/font/overflow checks validate declared requirements at desktop/mobile viewports. The repaired mobile screenshot was visually inspected. Pixel-perfect/reference semantic comparison is not claimed.

27. **Browser/DOM inspection.** Existing Qt profile/pages, verified navigation and semantic/action locators are reused. The real counter click changes observed text to `Count: 1`; actual console errors fail UI health. Requested and observed responsive viewport dimensions must match.

28. **Repair architecture.** Actual failures create issues; an approved changed source patch returns through owned staging/integration and the entire validation loop. Configured shared models can propose one compact file repair; caller callbacks can supply broader reviewed patches. Model command/permission declarations cannot authorize execution.

29. **Maximum bounds.** Default three changed repair rounds, two attempts per issue, eight shared calls, Phase 2 token budget and 300 seconds of build execution. Generation has a clamped maximum 60-second stage; cleanup has short separate bounds. Default proposals: 80 files/20 MB total; copied workspaces: 6,000 files/20 MB each; at most eight scopes. Resident past sessions are bounded to 20.

30. **Issues.** Bounded deduplicated issue records contain stage/category/severity, actual redacted evidence, status, affected requirement IDs, repair attempts and resolution. Permission/environment/test/build/runtime/visual/integration/requirement/artifact failures remain distinct.

31. **DefinitionOfDone.** Source, dependencies, build, tests, runtime and artifacts must pass; web also requires UI. Every nonoptional requirement must be done from actual supported evidence. Unknown/warning/unavailable critical health is never verified.

32. **Requirements verification.** Supported checks consume actual CLI output, API response evidence, declared layout geometry, post-interaction DOM state and artifacts. Unknown requirements remain visible and partial. Generic calculator/multiplication requests cannot inherit addition-only acceptance.

33. **Artifacts.** Real archives are reopened/tested and hashed; source archive entries must match the integrated hashes. Expected native outputs require explicit paths, actual nonempty files and shared verification. Local screenshots and archives are retained with hashes in controlled demo evidence.

34. **Checkpoint/resume.** Atomic typed sessions and shared graph checkpoints retain requirements, ownership, hashes, completed work, issues and budgets. Diagnostic secrets/approval tokens are redacted/excluded. Resume rechecks current files and reacquires authority; user changes are preserved and require review. Completed patches are not blindly repeated.

35. **Cancellation.** Linked existing tokens stop the build and its owned processes. A short physical terminal teardown wait runs in the driver outside the worker pool. Leases are retained while actual work remains; cancellation/resume fixtures leave no owned processes or resource leases.

36. **Dirty worktree.** An unrelated dirty README and secret fixture are preserved byte for byte. Stale and late root modifications are rejected rather than overwritten. Existing user changes in this repository and deleted screenshots were left intact.

37. **Secrets.** Protected paths/private keys/credential files are excluded from copies, snapshots and source archives. Known environment secrets and credential assignments are masked in diagnostics; credential material in generated source is rejected. This protection is not an assertion that every arbitrary file is classified perfectly.

38. **Repository injection.** Source/tool data carries untrusted provenance and cannot create authority tokens. The controlled injection README does not authorize uploads or Git actions. Indexed/requested source context is bounded and ranked before sending it to the shared model.

39. **Git safety.** Staging avoids Git mutations; known commit/push/merge/tag/rebase/reset/clean/publication commands are refused by the local driver. Git fingerprint/status/diff inspection is read-only. Arbitrary code execution is not an OS sandbox; indirect hostile side effects require stronger isolation.

40. **Web demo.** `build/phase4-demos/results.json` records a real multi-file dashboard, tests, owned HTTP server, counter click, failed CSS layout observation, repaired build/run/inspection and final archive. Actual PNGs are `web_visual_repair-0.png` (failure), `-1.png` (desktop repair) and `-2.png` (mobile repair).

41. **Python demo.** The actual addition CLI builds, runs real tests, prints 5 for 2 and 3, packages real files and passes all critical health/requirements. No text-only success or fake executable was produced.

42. **Parallel demo.** Actual implementation/check graphs reach four bounded workers on six ownership scopes with 50 Python source/test files in the benchmark. Real cross-module integration tests, CLI execution and package/source hash checks pass. Private ownership plus atomic integration prevents conflicting writers.

43. **Failure/repair demo.** The `a - b` implementation causes two actual assertion failures; a source-only `a + b` repair is staged, integrated, tested and run again. Failure evidence/history remains recorded, with one changed repair round.

44. **Visual repair demo.** The sidebar/main overlap fails actual DOM/screenshot verification. CSS is changed, rebuilt, tested, clicked and inspected again at 1000×720 and 390×720. One changed repair round resolves the issue; a separate thrown JavaScript exception remains failed.

45. **Existing-project demo.** Existing dirty/injection/secret files are preserved while owned new source is integrated and validated. Tests also cover existing source baseline conflicts and user changes during/after builds.

46. **Cancellation/resume demo.** An actual long-running test child is cancelled and reaped; a persisted session resumes with fresh authority and real tests. Applied files are reused by actual hash, and integration patch count does not increase on safe resume. Integration undo uses the existing UndoStore and preserves unrelated files.

47. **Sequential benchmark.** Fresh services/journal per sample; median of three runs: small project **2417.22 ms**, 50-file/six-scope project **7671.65 ms**. Same actual implementation-through-final-verification pipeline, with no artificial waits.

48. **Parallel benchmark.** Corresponding medians: **2210.14 ms** and **6689.74 ms**; peak workers two and four respectively. All 12 benchmark project runs were verified. Raw samples are in `build/phase4-benchmark.json`.

49. **Measured comparison.** Speedup **1.094×** small and **1.147×** multi-scope (about 8.6% and 12.8% lower elapsed time). An earlier shared-journal run showed slowdown and exposed benchmark ordering/cache bias; final samples isolate runtime state. These host measurements do not establish universal or LLM speedup.

50. **CPU/RAM.** Final benchmark wall **60.99 s**, process CPU **30.89 s** (50.65% of one core on average), peak process RSS **126.57 MiB**. Live Qt demo process RSS was **236.97 MiB**. Child CPU/RAM and all host load are not included in these process measurements.

51. **GPU/VRAM.** Host end samples reported **0% / 0 MiB**. No real local model was loaded for these deterministic build measurements. Shared inference resource/budget wiring is tested, but real model quality/latency/VRAM behavior is not claimed.

52. **Tests added.** 37 runtime cases and one real-browser subprocess case: 38 new cases. Existing GUI tests additionally wait for actual background completion and retain apply/undo behavior. Tests cover real effects and important negative cases rather than mirroring implementation.

53. **Targeted results.** Final selection: **46 passed, 42 deselected, 118.49 s**, in `build/phase4-final-targeted.log`. A final rendered-browser regression also passed after an input-order guard was added before temporary viewport resizing. Earlier foundation tests and actual Phase 3 integration were also run. Audit defects were corrected before the final green selections.

54. **Complete regression.** **735 passed, 59 subtests passed, 217.47 s**, in `build/phase4-full-tests.log`. This includes kernel/agents/actions, models/providers, voice/speech/wake, PC/files, visualization/simulations, pets, research, settings/history and project workflows.

55. **Startup.** Isolated actual services/main-window startup: constructor **203.47 ms**, UI/health **1185.83 ms**, **zero critical failures**, 60 startup capabilities, nine roles, same shared kernel, attached browser, lazy agent pool and lazy builder, zero leases after shutdown. `build/phase4-startup.json` records the sample.

56. **Packaging.** Local `build/phase4-package/morice_ai-0.8.0-py3-none-any.whl`: **1,951,234 bytes**, all **42** runtime modules equal source, valid ZIP integrity, SHA-256 `df80cb6f2edb0e38c4081e48f9969a221087c2fd1f828570c3e5b6eb701e0437`. Frozen spec includes the helper; installed Python/tooling remains required. No new portable executable or public release was claimed.

57. **Performance regressions.** Direct kernel echo median **0.2747 ms** over 250 calls, versus the recorded Phase 3 sample about 0.252 ms: roughly +0.023 ms and no agent dispatch. Startup remains lazy; single samples vary and are not a statistical no-regression claim. Real full-project validation adds purposeful process/readback/checkpoint cost. Simple deterministic actions and one-file text edits keep their bypass routes.

58. **Remaining limitations.** No universal semantic vision/UIA, reference screenshot similarity, generic desktop/native/mobile/editor play-mode, database/auth persistence or comprehensive accessibility/performance certification. Complex generation and automatic repair depend on a configured real backend; default automatic repair is one compact file and backend usage counts may be estimates. Online documentation is not automatically added to compact generation. Static command gates do not sandbox arbitrary project/package code. Direct/uncooperative providers can retain leases; physical teardown can extend wall time. See the guide/audit for concrete boundaries.

59. **Phase 5 readiness.** Ready to extend existing serializable sessions/task/result contracts and node-scoped resources into user-authorized device work. No remote-device protocols, distributed workers or Phase 5 implementation were added here.

60. **Phase 6 readiness.** Existing researcher/analyst/simulation/verifier roles can consume real build/test/observed artifacts and issue evidence. No new scientific laboratory or Phase 6 implementation was added here; provider/tooling limits remain explicit.

61. **Phase 7 readiness.** Owned sessions, independent verification, bounded repair, checkpoints and exact authority provide an integration base. Broader autonomy still requires stronger hostile-code isolation, external-effect controls, semantic providers and platform observers. No deployment ecosystem or Phase 7 implementation was started.

All operations remained local: edit, inspect, build, run, test, benchmark and package. No commit, push, merge, tag, rebase, reset, clean, release, deployment, public upload or public website modification was performed. Review the architecture/API in `project-builder-2.md` and the fresh audit in `project-builder-2-audit.md`.
