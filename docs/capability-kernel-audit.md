# Phase 1 execution architecture audit

Audited the working checkout at `E:\MORICE` on 2026-10-03. Existing local edits were preserved. Evidence below comes from executable paths rather than previous reports.

| Component | Current implementation / execution evidence | Reusable | Limitation | Migration action |
| --- | --- | --- | --- | --- |
| Application entry | `morice_app_launcher.py` -> `pyside_app.run_app` -> `MoriceWindow` -> `RuntimeServices` | Yes | Large Qt coordinator | Own kernel in runtime services; preserve signal delivery |
| Background execution | `runtime_services.BackgroundTaskManager`, used by `_start_background_task` | Yes | Futures lack dependency/state/resource contracts | Reuse interactive/background pools for graph submission |
| Tools | `agent_tools.ToolRegistry` and `AgentToolExecutor`; UI calls executor directly for patch/index/git/terminal | Yes | A plain returned value becomes verified automatically; timeout may detach work | Adapt representative handlers; explicit verification and cancellation |
| Project mutation | `BuiltinTools._apply_patch`, scoped grants, atomic writes, undo, baseline hashes | Yes | Separate task lifecycle | Keep implementation and permission gates behind adapter |
| PC fast path | `FastActionRouter` -> UI confirmation -> `ControlProviderRegistry.execute` | Yes | No common task/resource state | Route registered actions through kernel; retain broker and verifier |
| Verification | `ControlResult.verified`, `ToolResult.verified`, renderer plugin validation | Yes | Different formats and no common override contract | Normalize results; verifier can reject attempted success |
| Structured context | `unified_intelligence.WorkingMemory`, `DesktopContext`, project request context | Yes | Runtime unified registry starts empty; multiple context sources | Resolver wraps memory and observes current desktop/project fields |
| Permissions | Tool `PermissionPolicy`, PC `PermissionBroker`, unified `PermissionController` | Yes | Separate domain policy authorities | One kernel authorization facade delegates to existing authorities |
| Goals | `GoalExecutionOrchestrator` compiles capability calls; device controller uses unified permissions | Partial | Specialized existing goal state and planner, separate execution path | Keep compatibility; future plans lower into kernel TaskGraph |
| Persistence | ActionHistory JSONL, recovery atomic JSON, settings, research store | Yes | No safe graph checkpoint | JSON graph serialization; do not add database |
| Events | Qt signals, goal status callback, pet event scheduler | Partial | No general typed internal execution bus; pet scheduler is domain specific | Lightweight typed kernel bus, bridge Qt through existing signals |
| Timing | PerformanceProfiler, StructuredLogManager, realtime trace | Yes | No task/attempt correlation across domains | Bounded kernel timing records forwarded into existing profiler/logs |
| Resources | Renderer ResourceManager is an artifact cache; GPU lock is inference-specific | Partial | No task resource leases or foreground ownership | Add atomic node-scoped leases; preserve cache/GPU implementation |
| Visualization | VisualizationManager -> renderer registry -> render/validate -> Qt signal | Yes | Separate artifact scheduling/cache needed | Register a lazy graph artifact adapter using existing plugin |
| Voice/model/research/node | Runtime-owned services and domain implementations | Yes | Domain-specific execution/policy | Leave operational; migration map for later phases |

No new planner, remote pairing, research engine, agent swarm, or connector is part of this phase.
