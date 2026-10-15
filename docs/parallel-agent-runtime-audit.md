# Phase 2 foundation audit

The requested checkout is `E:\MORICE`. The supplied desktop working directory
`D:\MORICE` does not exist on this host. Work used the existing E: checkout.
Existing user changes and staged files were preserved; no Git mutations were made.

## Verified Phase 1 foundation

The audit read implementation and call sites, then ran the existing kernel and
runtime tests: **50 passed in 9.47 seconds**. An expanded compatibility run before
the new tests passed **72 tests**. Phase 1 was operational, rather than just documented.

| Existing implementation | Actual behavior | Phase 2 decision |
| --- | --- | --- |
| `morice/kernel/tasks.py` | Typed nodes; dependency policies; atomic claims; cycle validation; JSON graph persistence | Reuse this graph. Lock snapshots and reject adding tasks during execution. |
| `morice/kernel/execution.py` | Permissions, cancellation, deadlines, bounded retries, atomic leases, verification overrides | Every worker uses `run_task`; preserve failed process output and remove duplicate evidence. |
| `morice/kernel/scheduler.py` | Reserved interactive/background graph lanes, sequential graph execution | Extend with a bounded shared DAG worker pool; retain existing direct and sequential paths. |
| `morice/kernel/resources.py` | Atomic all-or-none node-scoped leases, exclusive foreground UI | Add descriptor lookup for plan validation; register CPU/IO/model/GPU/VRAM budgets. |
| `morice/kernel/events.py` | Ordered bounded events, weak subscriptions, callback isolation | Add workflow, worker, wait and resume events; reuse this bus. |
| `morice/kernel/context.py` | Existing WorkingMemory, references and structured capture | Reuse capture; build small role-specific packets above it. |
| `morice/kernel/adapters.py` | Existing safe tools, PC providers, file previews, calculation and graphs | Reuse real implementations; retain failed subprocess logs for Tester. |
| `morice/agent_orchestrator.py` | Intent/model routing, project indexing and linear legacy tool execution | Add workflow planning entry point; preserve legacy tool execution. |
| `morice/model_router.py` | Intent profiles, configured candidates, model health | Share this router; configure shared backend callbacks without loading worker models. |
| `morice/runtime_services.py` | Lifecycle, profiler, permissions, background workers | Own one coordinator; include status in snapshots; cancel agents before kernel shutdown. |
| `morice/pyside_app.py` | Direct PC routing and Qt signals for background results | Keep PC first; route supported complex workflows afterward; use signals and main-thread timers. |
| `morice/research/simulations.py` | Four real fixed deterministic local models | Lazy capability adapter; no additional laboratory implementation. |
| `morice/web_search.py`, `morice/vision.py` | Existing web search; image metadata with OCR unavailable | Reuse these limited adapters; do not report unsupported browsing/vision as verified. |

## Hardware evidence

`Get-CimInstance Win32_ComputerSystem` reported 16 logical CPUs and
16,873,545,728 bytes of physical RAM. `nvidia-smi` reported an NVIDIA GeForce
RTX 3050 6GB Laptop GPU with **6144 MiB** VRAM. The initial GPU sample showed
91 MiB used and 0% utilization. GPU state can change during ordinary desktop use.

Defaults therefore use four workers, two CPU tasks, four IO tasks, two admitted
workflows, and one local model request. The model capability reserves the local
GPU and its configured VRAM budget. Other tool work can overlap inference.
Startup does not load a model or run a GPU probe to configure workers.

## Corrections discovered during implementation

1. Failed legacy tools previously lost their structured output at the kernel
   adapter. Retain stdout/stderr/exit code so actual failed tests remain evidence.
2. Verification evidence could appear twice. Preserve ordered unique evidence.
3. Workers executing shared graph nodes could expose success before shared-state
   commit. Execute copies and commit collected results in the driver.
4. Result events under coordinator locks could invert locks with a status
   subscriber. Publish after releasing coordinator/state locks.
5. A sequential first run could accidentally initialize a permanently serial
   pool. Pool capacity is independent of a workflow's sequential mode.
6. Windows RAM telemetry used an implicitly truncated process handle. Use explicit
   pointer types; the actual memory probe now returns a positive working set.
7. Completed artifact/input changes could leave cached results apparently valid.
   Record plan fingerprints, read back artifacts, and block affected descendants.
8. Resource waits originally appeared as running work. Emit real wait/resume
   events and derive activity from explicit worker states.

## Final fresh code review

Reviewed admission limits, dependency commit order, cancellation races, timeout
cleanup, event lock ordering, Qt calls, model sharing, packet provenance, role
permissions, duplicate tasks, file baselines, checkpoint signatures and bounded
history. Added tests for issues found. This was a fresh review of the implementation,
not a claim that a separate human reviewer approved it.

The original safe domain authorities remain responsible for exact file/process
approvals. Workers cannot authorize themselves, spawn other workers, or replace
their assigned capability from source text. No private reasoning is included in
status or activity records.
