# Project Builder 2.0 foundation audit

Date: 2026-10-04. Working repository: `E:\MORICE`.

The live kernel, agent runtime, and action runtime were inspected, rather than relying only on their reports. Registry/health/schema checks, typed TaskGraph and results, centralized permissions, shared resource admission, bounded WorkerManager, SharedTaskState, AgentCoordinator checkpoints, desired-state bindings, independent observations, actual domain verification, cancellation, and the durable action journal are present. The foundation selection passed **148 tests and eight subtests in 26.21 seconds**, including the real Phase 3 browser/process/window integration and existing builder/workflow tests (`build/phase4-foundation-tests.log`).

Existing project architecture:

- `project_builder.py`: request/language/framework understanding, acceptance contracts, manifest validation, and limited deterministic scaffolds.
- `project_index.py`: bounded incremental file/symbol/framework/dependency/Git indexing.
- `agent_tools.py`: preview baselines, atomic patch apply, UndoStore, terminal process ownership/cancellation, source validation, and read-only Git inspection.
- `project_workflows.py`: manifest/marker-based adapters for web, Python, Node, .NET, Java, Rust, Go, Android and game editors, plus executable discovery and artifact checks.
- `project_runtime.py`: file validation and launch plans; legacy launches do not independently prove a healthy runtime.
- `autonomous_builder.py`: persisted plan, file checks, build/test commands, and a callback-driven bounded repair loop.
- Project Mode: one existing frontend with folder/full-access policy, model manifest generation, diff review/apply/undo, command output, and source verification.

Concrete Phase 4 gaps:

- The legacy builder invokes subprocesses directly instead of the shared verified-action execution boundary.
- Its `verified` command state can omit runtime or visual validation; unknown critical health is not a full project DefinitionOfDone.
- Requirements and architecture are not independently tracked through implementation and repair.
- Existing coding workers accept concrete candidates, but there is no integrated ownership/staging strategy for parallel changes in one project.
- There is no project-specific safe resume/invalidation path combining actual baselines, completed work, run evidence, and bounded repair history.
- UI source/patch verification and launch acknowledgement can be confused with a working application.

Phase 4 will extend this architecture. It will use the same AgentCoordinator, TaskGraph, WorkerManager, permissions, resource leases, action bindings, and UndoStore. Environment detection remains lazy; unsupported installed tooling and semantic vision limitations remain explicit. All source-control/publication restrictions remain in force.

## Fresh implementation audit

The final implementation was read again against the live call paths and exercised through actual effects. The new project package is attached lazily to the existing AutonomousBuilder; it has no independent scheduler, executor, model loader, permission broker or unbounded worker pool. Project tasks pass through existing AgentCoordinator validation, role capability restrictions, SharedTaskState, WorkerManager and CapabilityKernel. Existing contracts and authorities remain responsible for execution and verification.

The audit found and corrected these concrete defects before delivery:

- A repaired private copy incorrectly reused the original project baseline. Private copies now get actual private hashes; integration keeps the reviewed root hashes.
- New-file patches included an empty SHA-256 field rejected by the existing schema. New files now carry only `expected_exists=False`; GUI previews follow the same contract.
- A screenshot could pass responsive checks without proving the requested viewport. Inspections now temporarily constrain the actual view size, restore its prior bounds, and compare requested and observed viewport dimensions.
- Background stdout used a shared/unbounded temporary file. Owned processes now use two application-capacity-bounded pipe readers with 8 KiB tails, preserve leases until teardown and reject uncompleted cleanup.
- Logical cancellation could finish before a terminal adapter removed its actual process. The project driver now performs a short ownership-scoped physical cleanup wait outside the worker pool, retaining existing leases.
- A stale archive or a source edit after runtime validation could otherwise retain earlier success. Archive entries are checked against integrated hashes and source hashes are checked again at the end.
- Automatic repairs could refresh a user-modified root baseline. Both unapplied reviewed paths and applied owned paths are checked before repair; changed user data requires a fresh review.
- A redirected cache, Windows device/ambiguous filename, case alias or metadata path could escape ownership assumptions. Resolved cache/root bounds and Windows path protections now reject these cases.
- Empty test runs could be mistaken for testing. Actual zero-test runner output now fails test health.
- A generic calculator request could receive an overly broad success claim from an addition scaffold. Only the narrow explicit addition contract receives automatic acceptance; other behavior remains unverified or uses configured source generation.
- The GUI initially tracked only source completion and did not retain the integration UndoStore identifier. Background build results now carry final health/requirements and the actual root integration undo ID.
- A growing shared journal skewed the sequential/parallel benchmark. Final samples use fresh services and journals for both modes. A transient GUI initialization order error was also corrected before the final startup/regression checks.

## Evidence and negative cases

`tests/test_project_build_runtime.py` uses actual isolated filesystem patches, source/compiler checks, Python tests, CLI runs, ZIP readback, a local HTTP API and actual Popen cancellation. It verifies permission denial, stale user baselines, unrelated dirty files, secret redaction/exclusion, rejected publication commands, unknown requirements, exhausted/no-op repairs, protected tests, requirement invalidation, unavailable model proposals, shared generation/repair budgets, source edits after validation, local environment preparation, ownership and integration undo.

`tests/test_project_build_browser.py` launches a fresh Qt/Chromium process and drives `scripts/demo_project_builder.py`. The application has separate HTML/CSS/JS files, a sidebar and a real counter. An intentionally overlapping layout creates actual failed screenshot/DOM evidence; the CSS repair is rebuilt, tested, run, clicked and inspected at 1000×720 and 390×720. A separate actual JavaScript exception fails UI verification. Python assertion failures are repaired and retested. Dirty/injection/secret fixtures remain unchanged. Cancel/resume finishes without duplicated integration patches, owned processes or held leases.

The GUI compatibility tests wait for actual background completion before deleting their isolated project directories. They retain folder preview/apply/reject, atomic file writes, full-access behavior and UndoStore restoration. They do not relax failing behavior or replace acceptance tests with success stubs.

Foundation and performance evidence is recorded in `build/phase4-foundation-tests.log`, `phase4-final-targeted.log`, `phase4-full-tests.log`, `phase4-demos/results.json`, `phase4-benchmark.json`, `phase4-startup.json` and `phase4-package-verification.json`. The delivery report gives exact final counts and measurements.

## Remaining constraints verified rather than hidden

The five explicit Phase 2 integration limitations remain accounted for: actual browser navigation/DOM state and rendered screenshot evidence extend snippet search; semantic vision still needs an installed/configured provider; the project observe/repair loop is complete for supported controlled web/CLI/API contracts while universal desktop UIA is unavailable; process/readiness waits run outside the bounded worker pool and busy resources still use Phase 2 admission; small deterministic PC actions and simple source edits keep their direct paths.

Full semantic visual comparison, user-reference image similarity, accessibility/contrast/keyboard auditing, database persistence/auth checks, arbitrary desktop GUI workflows, Android/device execution and Unity/Unreal/Godot editor play-mode require further observable contracts and installed tooling. Node/.NET/Java/Rust/Go/mobile/editor adapters were detected, not certified end to end. Unknown critical health cannot become verified.

Model proposal/repair wiring is exercised with bounded configured callback fixtures. No large local model or real inference-quality benchmark was loaded for this delivery. Automatic repair currently has a compact one-file source budget; larger reviewed patches can be supplied through the API. Shared generation uses local indexed context; online documentation is not automatically retrieved into that compact prompt.

Permission and static command gates do not constitute an OS sandbox. Arbitrary source/package scripts may have indirect effects; hostile-code isolation and comprehensive external-effect enforcement remain technical constraints. The project driver itself performs no commit, push, merge, tag, rebase, reset, clean, release, deployment or publication. Independent authority is still required for browser clicks/submits/uploads. Direct/uncooperative provider work may retain leases beyond logical cancellation; no lease is falsely released to claim cleanup.

Final wheel checks compare all 42 kernel/agent/action/project modules with current source. The frozen spec includes the standalone build helper and avoids launching the MORICE executable as a Python interpreter. A portable executable was not rebuilt or released; installed Python and platform tools remain necessary where used. Existing unrelated user edits and deleted screenshots were preserved.
