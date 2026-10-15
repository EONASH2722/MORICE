# MORICE Phase 8 completion report

Phase 8 hardens and validates the shared Phases 1–7 systems. The final source passes **875 tests and 62 subtests**, and both final repeat runs pass all **31 Phase 8 tests**. Real local acceptance, fault recovery, cancellation/resume, a 10,000-run research sweep, five/ten mutually authenticated protocol nodes, actual CUDA model execution, wheel parity and a native frozen executable are validated. Phase 9 implementation has not started.

Validation is on Windows 11 build 26200, Python 3.14.2, Intel i5-13450HX with 16 logical processors, approximately 15.7 GiB RAM and an RTX 3050 6GB Laptop GPU. The working checkout is `E:\MORICE`, as specified by the Phase 8 attachment. Local fixtures and provider/hardware constraints are qualified below. This is controlled integration readiness, not universal production certification.

The architecture and operations guide is [full-stack-hardening.md](full-stack-hardening.md); the separate review is [full-stack-hardening-audit.md](full-stack-hardening-audit.md). The machine-readable final evidence index is `build/phase8-completion.json`. No commit, push, merge, tag, deployment, external publication or Phase 9 model installation was performed. Preexisting user changes and screenshot deletions were preserved.

## Measured performance

The before source is extracted from the preserved Phase 7 wheel, SHA-256 `d6b2f8c023575e1564fe9c2414fec8721a406286c2f5433f7817be82fe29d04b`. Both sides use the corrected same harness, one application runtime, actual startup health, six seconds of settling and three seconds of idle observation excluding expensive observer snapshots from CPU time. Each has three fresh processes, 300 calculations and 10,000 event publications per process.

| Observation | Phase 7 baseline | Final Phase 8 |
|---|---:|---:|
| Source readiness median | 5,848.24 ms | 3,734.36 ms |
| Largest source startup sample | 46,402.39 ms | 4,008.05 ms |
| Idle CPU median, percent of one core | 63.146% | 3.117% |
| Idle process RSS median | 313,233,408 bytes | 312,647,680 bytes |
| Idle threads median | 74 | 74 |
| Idle Windows handles median | 1,076 | 1,076 |
| Owned child processes / sockets at idle | 0 / 0 | 0 / 0 |
| Median of calculation p50 values | 1.0622 ms | 1.6753 ms |
| Median of calculation p95 values | 2.7417 ms | 3.3900 ms |

Startup observations are sequential and filesystem/code-cache sensitive; the 46.4-second first baseline sample is retained. Three-run p95 is the maximum sample, not a robust population percentile. The report does not attribute every startup difference to a specific edit. Direct calculation p50 has a measured 57.7% relative regression, adding about **0.61 ms**, from the hardening path; it is explicitly flagged in the comparison artifact. The final calculation p95 remains below the practical 10 ms budget. A fresh environment snapshot per diagnostic record reduced the initial hardening overhead without weakening credential rotation handling. Earlier observer-contaminated/two-runtime measurements are superseded.

The final 120-second steady-state soak performs **2,860 direct commands, 2,860 events, 286 real agent workflows and 286 verified remote commands**. RSS grows **1,499,136 bytes, approximately 1.43 MiB**; threads fall 97→94, handles 1,173→1,168, sockets stay at 21 while ten local nodes are live, and active leases/owned background processes stay zero at all steady samples. Runtime data totals 13,856,315 bytes. After close, leases, owned background processes, mesh sockets/listeners and pending workers are all zero. Whole-workflow duration is 172.82 seconds; its Qt heartbeat has 8,640 ticks and a 46.05 ms maximum gap. This is a two-minute soak, not an hours-long endurance test or an MTBF estimate.

## Factual reliability scorecard

| Area | Observed result | Scope and limits |
|---|---|---|
| Startup | Three final source samples, zero critical failures; native executable health succeeds | Actual source/native Qt; external GGUF absent in clean profiles is degraded chat |
| Idle | CPU/RSS/thread/handle/process/socket samples recorded | Three short settled samples; GPU data is host-wide |
| Fast path | 900 benchmark calculations succeed; p95 below 10 ms | Bypasses AgentCoordinator; cold tool/native application launch can be slower |
| Chat/model | Four streamed HTTP scenarios plus one actual agent model response complete | CUDA server token counts; prose is not scientifically verified |
| Voice | Three controlled timing runs prove audio-before-EOF and bounded barge-in | Controlled PCM provider/sink, no physical/cloud latency claim |
| Agents | Real independent tasks overlap with peak two workers | Tiny cold-first parallel case is slower than warm sequential work |
| Actions | Actual Chromium interaction and native Calculator opening verify | Grounded adapters; arbitrary-app semantic vision remains provider-dependent |
| Builder | Dashboard tests/build/run/render pass; one failing calculator is repaired | Actual subprocess/file/UI effects; installed project toolchains are required |
| Mesh | Five and ten live protocol nodes; remote calculations and artifact hash verify | Same Windows host, loopback pinned mutual TLS |
| Research | Actual SQLite contains 10,000 VALID sweep runs and passes integrity check | Ideal model assumptions; no empirical materials validation |
| Ambient/connectors | Completion notification after verified steps; eight HTTP chaos/recovery cases pass | GitHub fixture; production account/relay remains unvalidated |
| Security | Existing scoped monitoring, denial, quarantine/restore and owned-process tests pass | Defensive heuristics, no exhaustive malware or CVE claim |
| Shutdown | Final demos/soak/probes release owned workers, leases, sockets/listeners | Uncooperative native work retains ownership and reports dirty |
| Recovery | Controlled Builder repair, resume, mesh reconnect and observed crash effect pass | Small finite controlled samples; failures are preserved |
| Packaging | Exact wheel/embedded-executable source parity; isolated imports/native startup pass | Local onedir executable; no signed installer or cross-OS certification |

Expected injected failures are not counted as unexplained operational errors. First-pass ordinary operations, recovery outcomes and harness failures are distinguished in items 74–76. No marketing reliability grade is assigned.

## Required 86-item report

1. **Phase 1 status.** The existing CapabilityKernel remains the single execution, discovery, permission, resource and verification boundary. Its prerequisite tests and the final whole-suite regression pass. No replacement kernel was introduced.

2. **Phase 2 status.** TaskGraph, WorkerManager, AgentCoordinator, SharedTaskState, the existing roles and bounded worker pool remain shared. Actual scientific tasks overlap with two workers; direct actions bypass agent orchestration. Scheduler admission keeps queued resource waits outside occupied workers, while actual bounded I/O/verification work necessarily occupies its active execution slot.

3. **Phase 3 status.** Verified actions retain observe→act→observe→verify, durable intents, bounded recovery and restart observation. Actual browser navigation, DOM checks, screenshots and an interaction pass; search snippets alone are still not verified page navigation. Desktop state is grounded in process/window identities and focus/DPI checks. Arbitrary semantic screen understanding needs a configured available provider; unsupported/authenticated/ambiguous screens request review. Long resource waits are not added, and cheap deterministic commands remain direct. These explicitly address all five original Phase 2 limitation targets with implemented behavior or concrete provider/native constraints.

4. **Phase 4 status.** The existing Builder runs real implementation, dependency/build/test/run/render checks and independent artifact verification through the same authorities. The responsive dashboard, failing-test repair and cancelled checkpoint resume pass. Frozen project building still requires an installed suitable external interpreter/toolchain; the executable is not a bundled compiler environment.

5. **Phase 5 status.** Existing authenticated TLS pairing, node registry, scoped remote capabilities, transfer integrity, revocation and replay handling remain intact. Five and ten actual protocol nodes are exercised locally. Physical Android/Linux operation and external network topology are not newly certified.

6. **Phase 6 status.** Existing ResearchRuntime and Laboratory use the shared kernel/coordinator/actions, actual SQLite records, bounded simulations and reproducible export. A 10,000-point ideal-density sweep completes and all stored statuses are VALID. Immediate terminal-state/resume races were repaired without a second research scheduler.

7. **Phase 7 status.** Ambient, GitHub connector fixtures and opt-in defensive security continue through existing AutomationEngine, EventBus, coordinator, permissions and verified actions. The completion notification follows real verification; signed delivery, scopes, refresh, revocation, cooldown and containment regressions pass. Live production OAuth/HTTPS relay and comprehensive forensic collection remain constraints.

8. **Prerequisite repairs.** Re-ran 277 prerequisite tests successfully. The final audit repaired event/domain lock inversion, credential diagnostic leaks, corrupt-journal overwrite risk, checkpoint serialization races, research resume visibility, runtime side effects, model lease borrowing, permanent outage admission and Windows optional mesh metadata failure. Earlier actual failures/reproductions are retained rather than labeled successful.

9. **Architectural audit.** `scripts/audit_full_stack.py` inventories 166 modules and expected single execution-authority definitions. Its resolved static graph finds zero multi-module top-level cycles and function-scope cycle groups of sizes 15, 3, 2 and 2. Lazy dependency cycles are explicit; static inspection is complemented by actual initialization/shutdown tests.

10. **Duplicate-system findings.** No duplicate kernel, agent pool, action runtime, permission authority or mesh transport was added. `visualization.ResourceManager` is an existing renderer artifact cache, distinct from physical execution leases. Optional telemetry now reads the existing runtime, and UI background work receives that runtime explicitly.

11. **God-class findings.** The preexisting Qt application module remains approximately 16,541 lines; desktop/control integration modules are also large. Health reporting moved into a small helper and runtime side effects were removed. A broad UI rewrite was avoided; large classes remain a documented maintenance constraint.

12. **Startup architecture.** Research, Mesh, Ambient, Builder project runtime and agent drivers remain lazy at ordinary startup. Heavy optional native dependencies are detected via metadata/spec and initialized on demand. Reduced-motion/hidden composer animation avoids an unnecessary idle timer, and diagnostics do not activate dormant subsystems.

13. **Startup before/after.** Corrected source readiness median is 5,848.24→3,734.36 ms. Final samples are 3,734.36, 4,008.05 and 3,582.58 ms; the 46,402.39 ms baseline outlier is preserved. All stage timings are in the two corrected JSON files; cache sensitivity prevents a blanket causal speedup claim.

14. **Idle CPU.** Baseline settled samples are 73.88%, 63.15% and 50.45% of one core. Final samples are 4.68%, 3.12% and 2.08%, median 3.117%. This is process CPU, not total-system percentage, and expensive psutil snapshots are excluded from the timed idle interval.

15. **Idle RAM.** Final whole-process idle RSS ranges 311,984,128–312,778,752 bytes, approximately 297.5–298.3 MiB. Median 312,647,680 bytes is close to the baseline 313,233,408 bytes. This is a whole-process working set including Qt/native components, not isolated allocations per subsystem.

16. **Idle GPU/VRAM.** The final no-model benchmark's host-wide sample is 2,386/6,144 MiB and 12% GPU utilization. Other desktop workloads are included, so this is not attributed to MORICE idle. The actual loaded 4B CUDA server sample reaches 5,765 MiB host-wide; after owned-server stop it returns to 2,329 MiB. Renderer software fallback and CUDA model execution are separate paths.

17. **Thread counts.** Idle source processes have 74–75 threads, including native Qt/library threads. The final enabled ten-node soak falls 97→94 threads rather than growing monotonically. The actual model server separately has 33 threads. Process exit, cooperative shutdown and pending-worker counts are recorded; not every native library thread is individually attributed.

18. **Process counts.** Final idle samples show zero owned child processes. Builder cancellation and demo cleanup show zero owned background processes; actual subprocesses are used and stopped. The user-facing Calculator is an intentional native application effect and is not falsely counted as a Builder-owned background process.

19. **Socket counts.** Source idle samples have zero sockets. Ten live local nodes hold 21 process sockets during steady soak. Final mesh sockets/listeners are zero after explicit close. These are owned-process/protocol measurements; they do not count unrelated host applications.

20. **File-handle findings.** Idle samples show 20 open files and 1,074–1,079 Windows handles. Soak handles fall 1,173→1,168. Native caches/Qt objects remain within a live process until its exit; the evidence supports bounded observed trends rather than claiming every handle returns to an exact pre-import baseline.

21. **Memory soak results.** Final steady-state RSS is 314,056,704→315,555,840 bytes, growth 1,499,136 bytes (1.43 MiB) over 120 seconds with thousands of real operations. Every steady sample has zero active leases/owned background processes, at most 20 retained workflows and 2,000 log records. No hours-long or MTBF conclusion is drawn.

22. **Storage growth findings.** The final runtime directory totals 13,856,315 bytes, including persisted research evidence and rotating diagnostics. Logs/history/event/cache bounds are enforced; verified research/build archives and encrypted quarantine require explicit manual retention/archival. There is no automatic destructive cleanup of user files or claim that durable evidence has no storage cost.

23. **Resource-manager stress.** Existing atomic node-scoped leases reject over-capacity/exclusive work, release normal completions and retain uncertain physical ownership. The 4.5 GiB LLM + 3.5 GiB image reservation fails on a 6 GiB pool, then image admission succeeds after release. Remote-node model ownership cannot satisfy local chat, and independent suspended streams cannot borrow claims.

24. **Model benchmark.** Actual existing 4B Q5 GGUF runs on the existing CUDA llama-server and RTX 3050. Cold load is 13,958.29 ms. Cold-short/warm-short/long-context/tool-context streamed requests plus a shared agent call complete with actual server token counts. Agent decode speed is 39.59 tokens/s; measured end-to-end rate is 35.24 tokens/s. Owned-server stop is verified. No model was downloaded.

25. **Model contention.** Normal local chat, prewarm, prefix priming and agent calls reuse the existing model/GPU/VRAM admission. Busy work rejects promptly, admitted agents avoid double reservation, generator close releases ownership and unload refuses active leases. The actual model benchmark performs 113 direct calculations during generation; the first cold tool/import maximum is 523.60 ms and is not hidden as a warm latency. Cached weights still require physical residency accounting before Phase 9 allocation.

26. **Fast-path benchmark.** Three final processes each execute 300 direct calculations. Median p50 is 1.6753 ms, median p95 3.3900 ms and observed maximum 7.99 ms. A 25% relative comparison flags p50 regression; the absolute additional median cost is approximately 0.61 ms. The native “Open Calculator” route during Builder work uses no additional agent workflow/model and verifies in 3,695.31 ms, including cold application discovery/launch and observation.

27. **Chat latency.** Actual cold-short TTFT/total are 144.30/432.73 ms; warm-short 32.38/307.07 ms; long-context 1,662.33/3,097.13 ms; tool-context 327.65/1,123.58 ms. The agent request has TTFT 219.28 ms and total 1,816.12 ms. These bounded local requests do not certify every model/context combination. Model prose remains unverified; one scientific explanation was inaccurate, while the reported numbers came from independently verified tools.

28. **Voice latency.** Three actual VoiceRuntime runs with a controlled PCM provider/sink record text, TTS request, first sink write, generation EOF and interrupt clocks. Median first sink write is 0.5081 ms, largest 1.5251 ms, in this deliberately local fixture. These are framework timings, not audible/cloud speaker latency; no physical microphone/wake measurement is claimed.

29. **Streaming TTS verification.** Controlled TTS requests and audio sink writes occur before a held generation reaches EOF in all three recorded runs and the behavior test. Normal completion and interruption are measured separately because aborted text need not reach EOF. The fixture uses genuine VoiceRuntime streaming queues and request ownership, with synthetic provider output clearly labeled.

30. **Barge-in behavior.** Recorded interrupt median is 0.0491 ms, maximum 0.0608 ms, in the controlled sink. The old sink is aborted and receives no later writes; a subsequent answer has its own audio request and plays controlled bytes. Physical sink/driver buffering and microphone quality require separate device validation.

31. **Qt/UI responsiveness.** The native acceptance run has 3,361 heartbeat ticks with maximum gap 50.83 ms while actual building, research and mesh effects occur. The final loaded soak has 8,640 ticks, maximum gap 46.05 ms. The actual frozen UI also pumps successfully. Existing focus/theme/reduced-motion/DPI coverage passes; there is no formal accessibility certification.

32. **Event-bus stress.** Four concurrent publishers send 10,000 events with bounded delivery/drop accounting, unique delivery, unsubscribe and no deadlock. Each benchmark also performs 10,000 ordered publications; final per-process p95 values are approximately 0.0057–0.0064 ms. Concurrent publishers may return before the single FIFO drainer invokes their callback; consumers must use the documented event semantics.

33. **Ambient trigger stress.** Existing 10,000-envelope flood tests enforce bounded queueing, cooldown, dedupe, causal depth and independent direct calculation. The final steady soak publishes 2,860 additional events and drives the existing scheduler, with no background model manufacturing of deterministic results. Completion emits one local notice after verified work; unsupported semantic watches remain unavailable.

34. **Connector chaos.** Eight real loopback cases cover 401, 403, 429, 500, timeout, connection reset, invalid JSON and refused connection. Each fails truthfully, stays within its asserted two-second test budget, releases leases and subsequently verifies a fresh object. Health refresh is forced to prevent a warm cache masking outage admission. Retry cooldown rejects without another HTTP call; auth expiry requires explicit fixture reauthorization. Live production OAuth/relay latency is unvalidated.

35. **Device Mesh chaos.** Actual offline dispatch is rejected, reconnect succeeds and revoked-peer dispatch is rejected. Existing tests cover malformed frames, replay, disconnect-after-mutation reconciliation, durable interrupted commands, corrupted/partial/resumed transfers and scope denial. The demo measures 5/10 live full-protocol local nodes, not synthetic node dictionaries or physical device fleets.

36. **Research stress.** The final 10,000-run sweep completes through the existing Laboratory and shared authorities; direct commands continue during work. Read-only inspection of the native acceptance database confirms 10,000 VALID rows and `PRAGMA integrity_check` returns `ok`. Existing real pause/cancel/resume, source freshness, units, bounds, analysis and export regressions pass. Scientific model assumptions remain explicit.

37. **Project Builder stress.** The dashboard actually runs dependency/build/test/run/render stages, a browser button changes state, layout checks and screenshots verify at desktop/mobile sizes, and an actual ZIP is independently hashed. The controlled calculator test genuinely fails before repair, then passes through the existing bounded repair loop. Parallel ownership/staging/path and existing toolchain tests pass under the same full regression.

38. **Action-runtime chaos.** Denied, ambiguous, unsupported, wrong-process, focus-changed, modal and unverified outcomes cannot become verified success. Corrupt journal blocks mutation while direct echo remains usable. Actual native Calculator, real Chromium interaction and existing process/file evidence use current observers rather than requested-state assumptions.

39. **Crash recovery.** An owned child performs an actual file mutation and is killed before verification. Restart sees the persisted executing intent, hashes the real file and reconciles it successfully; a replacement mutating handler records zero invocations. Original evidence survives and no automatic mutation replay occurs.

40. **Checkpoint corruption handling.** Agent restore rejects truncated JSON, nonobject roots, unsupported versions and invalid record shape without admitting work or overwriting bytes. Action journal rejects malformed entries/versions and input beyond its 16 MiB bound. Agent/Builder checkpoint reads are bounded at 64 MiB; atomic/flushed writes preserve durable state. Database failure is not repaired by deleting data.

41. **Cancellation audit.** Actual Builder process cancellation in native acceptance acknowledges in 328.36 ms and leaves zero owned background processes. Existing Research pause/cancel/resume, agent queued/running work, mesh streams and ambient slow-provider cancellation tests pass. Voice cancellation aborts old ownership. Native/uncooperative Python work remains cooperative and keeps truthful ownership until cleanup.

42. **Timeout audit.** Kernel deadlines, bounded subprocess waits, HTTP socket/total/byte budgets, browser observation limits and cancellation checkpoints remain active. Real delayed/reset/refused HTTP cases release resources. OS DNS/native calls can exceed a Python deadline; the runtime cannot safely force-kill an arbitrary Python thread and therefore reports remaining work rather than fake cleanup.

43. **Retry audit.** Existing per-task limits and explicit alternative action methods remain authoritative; identical unsafe mutation replay is forbidden. Builder repair is bounded and repeat signatures stop loops. HTTP cooldown/poll backoff uses due timestamps outside sleeping workers, and a unavailable provider can retry after refresh/cooldown. Denied/revoked scopes never become grants through a retry.

44. **No-fake-success audit.** Actual process exit, browser DOM/render/interaction, fresh provider object identity, independent scientific equations and artifact hashes determine tested success. The first incomplete-layout demo failed rather than turning green. Missing provider objects, wrong hashes, unsupported isolation, corrupt state and unconfirmed remote effects remain failed/blocked/inconclusive. Model prose and search snippets are not promoted to verified external facts.

45. **Permission audit.** The existing kernel permission manager and existing exact domain providers remain centralized. Denial precedence, task/capability/argument binding, one-use consumption, account scopes, process identity and target ownership are covered. No copied diagnostic/checkpoint field, external content or model lease grants authority.

46. **Risk audit.** Existing routine/read/write/high/destructive classes and consequence checks remain in effect. Controlled local tests explicitly configure their own approved scopes; production policy is not broadened. External provider writes, scoped termination/quarantine and browser submit/upload continue to require their existing exact approval contracts.

47. **Secret audit.** Synthetic nested API-key, Bearer, labeled-password, environment, rotating-environment and crash/journal canaries are absent from final persisted diagnostics. Exact reusable approvals are excluded. Package inventories exclude `.env`, personal settings/journals and default model weights. Unknown unlabeled private prose is not universally recognizable; original reproduction logs contain only deliberate synthetic test canaries and are retained as failure evidence.

48. **Prompt-injection audit.** Controlled connector issue text explicitly requests ignoring permissions and disclosing credentials, yet stays `UNTRUSTED_CONTENT`. Existing document/README/research/model-context boundaries never issue approvals or edit policies from content. The controlled cases and authority design pass; no claim is made that every linguistic variation has been exhaustively tested.

49. **Malformed-input audit.** Existing schema, finite numeric, maximum depth/item/string, bounded HTTP/frame/source/checkpoint and strict identity/path checks remain covered. Corrupt roots/versions and provider invalid JSON fail truthfully. Event/drop limits and bounded histories prevent unbounded queue amplification. Unsupported capabilities stay unavailable rather than returning fabricated placeholder output.

50. **Path/file race audit.** Existing exact project roots, ownership, baseline hashes, traversal/UNC/device-name/reparse/link checks, non-overwriting transfers and scoped quarantine verification remain exercised. Builder filename hashes such as `tokenizer.py` and long source survive diagnostic redaction. Checks are defensive contracts rather than a general OS sandbox for hostile arbitrary project code.

51. **Defensive-security audit.** Security remains disabled by default and limited to explicitly selected accessible process/listener/startup/log/file metadata and trusted indicators. Actual owned harmless process and encrypted quarantine/restore tests pass with exact approvals. A clean scoped collection is not a universal malware assessment; network isolation and exhaustive persistence forensics remain unavailable.

52. **Connector-security audit.** Existing OS-encrypted fixture credentials, explicit account scopes, official-origin rules, fixed-origin nonredirecting bounded transport, signed webhook verification, replay ledger, generation invalidation and denial behavior pass. The adapter remains GitHub-specific; provider-wide OAuth scope and production browser consent/HTTPS relay remain documented constraints.

53. **Device Mesh security audit.** Actual pairing confirmation, pinned mutual TLS, node identity, per-capability grants, revocation, replay rejection, node-scoped resources and independently verified transfer hashes remain intact. All nine remote calculations and the delivered archive verify. The controlled topology is one Windows host; physical Android/Linux trust/storage/OS permission behavior still needs device validation.

54. **Dependency audit.** `pip check` reports no broken requirements. Actual inventory includes PySide6 6.11.2, numpy 2.5.2, Pillow 12.3.0, sounddevice 0.5.6, vosk 0.3.45, pypdf 6.19.0, Pint 0.26.1, cryptography 46.0.7, psutil 7.2.2 and PyInstaller 6.22.2. Playwright and llama-cpp-python are absent; the tested browser/server paths use Qt Chromium and existing llama-server. Compatibility is measured on this Windows/Python combination; no exhaustive CVE scan or all-version claim.

55. **Storage/database audit.** Real SQLite transactions roll back an interrupted delete and preserve prior records. Final persisted sweep integrity is checked read-only. Versioned JSON inputs are bounded, graph snapshots are locked/atomic and corrupt evidence is preserved. Invalid database state surfaces errors; destructive autosalvage and automatic retention of all user evidence are not implemented.

56. **Shutdown behavior.** Runtime admission closes before callbacks/cleanup, then existing agents/services/transports/processes shut down and owned model unload is attempted. The final demo/soak and native probes report clean shutdown, zero remaining leases/pending workers and zero owned background processes/mesh sockets/listeners. No physical lease is released just to make the report clean.

57. **Dirty-restart behavior.** A test intentionally retains an actual physical lease; shutdown reports dirty and keeps the marker. Restart observation reconciles an actual interrupted effect without replay. A corrupt journal remains blocked. Unconfirmed remote effects retain ownership until close/reconciliation rather than hiding uncertainty as success.

58. **Local wheel result.** Built `build/phase8-package/morice_ai-0.8.0-py3-none-any.whl`, 2,068,793 bytes; SHA-256 `6b9878f2f6609c368529a2d0a066126aa50ca8fd7f313f1b263e63b825600056`. ZIP integrity and exact parity for all 166 Python modules pass. `python -I` imports the actual wheel outside the workspace, initializes shared research/ambient authorities, verifies 2+3 and shuts down with zero leases.

59. **Frozen Windows package result.** The existing PyInstaller pipeline builds `build/phase8-frozen/MORICE/MORICE.exe` locally. Output has 3,306 files totaling 929,759,139 bytes; executable SHA-256 `3ef8e9260f439c1272c43cb2945a3e4a975f3881ba5d4c5f00a0a1024d77323b`. The actual embedded PYZ matches current source for 164 modules; GUI intentionally omits two CLI-only modules. GGUF/vision weights are external by default. Optional QML/tzdata build warnings do not prevent the tested paths; unrelated optional paths are not certified.

60. **Clean-environment startup.** Actual native executable probes create a new profile, remove Python environment variables, restrict PATH to Windows system directories and run the full UI/health/shutdown. Release-profile and stricter-profile internal clocks are 19.19 and 10.76 seconds inclusive of three seconds pumping Qt, with 26 checks and zero critical failures. The final outside-checkout/system-PATH probe takes **12.75 seconds from process launch to exit**, including its three-second UI interval; its internal clock is 10.99 seconds and records 83 UI ticks. The receipt is `build/phase8-release-startup.json`, and the complete smoke is `build/phase8-isolated-startup-smoke.json`. Internal clocks exclude loader launch; cache-sensitive timings remain a performance limitation, not an omitted result.

61. **Configuration migration.** Existing settings merge missing fields with current defaults and normalize supported values; preceding preference/appearance/restart tests pass. Corrupt settings JSON is a critical health failure with preserved evidence. No new configuration schema migration is introduced. Missing external GGUF and absent optional providers degrade availability; a matrix of all historical profiles, installed toolchains and Windows versions remains untested.

62. **Unified UX findings.** One RuntimeServices owns application background jobs, status/permissions, shared result evidence and optional subsystem lifecycle. New health helpers fit the existing report rather than a second dashboard authority. Hidden/reduced-motion composer animation stops unnecessary work. Existing themes, keyboard palette, focus/DPI and layout tests pass; arbitrary semantic screen and formal accessibility remain provider/review constraints.

63. **Status/cancel UX.** During an actual running Builder test, the agent status reports 0/1 tasks complete, one running task, zero waits and zero failures. “Open Calculator” routes directly, verifies native observed state and leaves the active agent workflow set unchanged. Cancel then acknowledges and resume verifies the persisted session. Summaries expose task state/evidence, not private internal reasoning.

64. **Health/diagnostics implementation.** Existing HealthReport now includes kernel, roles, action-journal corruption, lazy Builder/Research/Mesh/Ambient, connectors, security, voice, semantic vision and current leases. It does not activate dormant systems or infer connectivity from configuration. Optional unavailable dependencies degrade the overall report. Native probes include actual assets/settings/provider status and shutdown evidence without reusable credentials.

65. **Acceptance-demo architecture.** One shared runtime drives owned HTTP connector read, independent scientific graph, recorded research/sweep/export, Builder dependency/build/test/run/render, real Chromium observation/interaction, actual paired TLS transfer/hash, completion event and local notice. Controlled repair and cancel/resume legs use the same runtime. Complete stage graphs, execution events, commands, outputs and verification evidence remain in JSON.

66. **Acceptance-demo result.** Final native-interaction acceptance completes in 67.24 seconds with no errors. Final current-source acceptance plus 120-second soak completes in 172.82 seconds with no errors. Calculated and simulated density agree at 1333.3333333333333 kg/m³ under explicit ideal-volume assumptions. Every shared-authority identity assertion is true, transfer verifies and notification follows successful consequential steps.

67. **Acceptance-demo parallelism.** Native acceptance's independent two-task graph has peak two workers and 371.03 ms wall time; sequential comparison has peak one and 9.74 ms. Cold Pint/tool initialization and scheduling dominate the first graph, so this demonstrates overlap rather than faster tiny-task execution. Zero model calls are used to manufacture deterministic science. Direct interactive commands continue during sweeps/model work.

68. **Acceptance-demo verification.** Calculation uses bounded AST/Pint dimensional checks and independent recomputation; simulation has explicit independent equations and provenance; SQLite contains actual outputs. Dashboard tests and process results are real, Chromium sees the readable density and changed button state, archive hashes match remote bytes, and each remote calculation has verified status. No acknowledgement alone establishes final success.

69. **Controlled failure recovery.** The deliberately broken addition implementation returns subtraction and genuinely fails pytest. Existing Builder repair changes the owned source, reruns checks and produces verified output with a retained repair history. Actual mesh reconnect also verifies; offline/revoked cases fail truthfully. Harness mistakes and early regressions remain separate recorded failures.

70. **Acceptance-demo cancellation.** A real 30-second Builder test process is cancelled after status/native interaction. Final native cancel latency is 328.36 ms; its state is cancelled and active owned processes are zero. Graph cancellation, UI heartbeat and final ownership cleanup are recorded rather than assuming cancellation from a flag alone.

71. **Acceptance-demo resume.** The cancelled Builder session is saved, its original safe commands restored, and existing checkpoint resume completes verified. Preceding Research immediate pause/cancel/resume behavior is also exercised. Interrupted mutating actions use observation/review rather than automatic replay or borrowed old approvals.

72. **Acceptance-demo artifacts.** Final artifacts are under `build/phase8-native-acceptance/4318db606acb4734aa76d68c970df864/` and `build/phase8-release-soak/8aab3add30624818845b5e881c9627ed/`. They include actual dashboard source/ZIP, desktop/mobile Chromium screenshots, command/repair evidence, research PDF/manifest/JSON/reproduction script/notebook, real SQLite records and paired-node inbox bytes. Evidence JSON records exact hashes and paths. Artifacts remain local for review.

73. **Reliability scorecard.** The factual table above covers startup, idle, fast path, chat, voice, agents, actions, Builder, Mesh, Research, Ambient/connectors, security, shutdown, recovery and packages. `build/phase8-completion.json` references final observations and finite sample counts. There is no inferred universal error rate, MTBF or unsupported reliability grade.

74. **First-attempt success.** Observed final ordinary legs include one first-pass dashboard, nine first-pass remote verified calculations, one verified transfer and one first-pass native Calculator request. The intentionally broken calculator has zero first-attempt success and one verified repair. The integration harness itself needed corrections: initial shape/layout assertions, soak deadlines/live-lease assertions and a native-route field error are retained, so overall harness first-attempt success is not presented as 100%. Samples changed during harness development and cannot estimate product-wide reliability.

75. **Recovery success.** Eight controlled connector fault cases each recover a verified fresh read after appropriate cooldown or explicit expired-auth fixture reauthorization. One controlled Builder repair, one Builder cancel/resume, one real mesh reconnect and one crash-observation-without-replay scenario succeed. These finite counts are scoped to those fixtures; revoked authorization is intentionally never “recovered” by bypassing denial.

76. **Resource leak results.** Final steady samples have zero live leases/owned background processes; all final close results have zero leases, background processes, mesh sockets/listeners and pending workers. Handles/RSS show bounded observed trends and histories hit their configured caps. Phase 8 fixtures assert lease cleanup; dirty-ownership cases deliberately retain then explicitly release their test lease. Native caches/other-host GPU allocations are not labeled leaks, and no exhaustive lifetime counters per every legacy test class are claimed.

77. **Tests added.** Four substantive Phase 8 modules add 31 tests: hardening/credential rotation, actual child crash/SQLite/checkpoint/voice/event stress, model ownership/admission and real HTTP chaos/recovery. New cases verify behavior and physical effects, not an implementation-shaped fake success. Existing fixture corrections preserve production verification and authority contracts.

78. **Targeted tests.** Prerequisite selection passes 277 tests; final broad audit selection passes 139 tests and 3 subtests; final connector/security/hardening selection passes 44 tests and 3 subtests. Final health-specific check passes 18 tests. Logs are `build/phase8-prerequisites.log`, `phase8-final-audit-tests.log`, `phase8-final-chaos-validated.log` and `phase8-final-health-tests.log`.

79. **Repeated/flaky-test results.** Both final complete Phase 8 selections pass 31 tests and 3 subtests: 7.33 seconds and 6.82 seconds. Earlier repeats also passed but predated final additions. The research terminal/resume race and host-dependent battery fixture were reproduced/corrected. Two repeats are controlled regression evidence, not a statistical proof of no future flakes.

80. **Complete regression suite.** Final current production source passes **875 tests and 62 subtests in 346.18 seconds** (5 minutes 46 seconds): `build/phase8-release-source-tests.log`. Earlier complete 865-test runs and the first three-failure run remain available. The final source includes all model node/suspended-stream, redaction, connector recovery and health changes.

81. **Benchmark artifact paths.** Corrected before: `build/phase8-before-corrected.json`; final after: `build/phase8-after-final.json`; comparison: `build/phase8-benchmark-comparison.json`; real CUDA model: `build/phase8-model.json`; controlled voice: `build/phase8-voice.json`; final loaded soak/native acceptance: the item 72 evidence files. Static/dependency inventory is `build/phase8-final-audit.json`. Earlier invalid/unsuccessful measurements are retained and superseded, never averaged into final success claims.

82. **Packaging artifact paths.** Wheel: `build/phase8-package/morice_ai-0.8.0-py3-none-any.whl`; frozen directory: `build/phase8-frozen/MORICE/`; parity/import/inventory: `build/phase8-package.json`; native outside-checkout launch: `build/phase8-release-startup.json` and `build/phase8-isolated-startup-smoke.json`. Build logs are `build/phase8-release-wheel-build.log` and `build/phase8-release-frozen-build.log`. Only local artifacts were created.

83. **Remaining limitations.** Short soak/sample size, source-cache sensitivity, slower frozen startup, small direct-p50 overhead, cold application/tool load, GPU host-wide attribution and persistent cached weights remain explicit. Live semantic vision, physical mic/wake/audibility/cloud TTS, production GitHub consent/HTTPS relay, physical Android/Linux, advanced adversarial-code isolation, installed project toolchains, formal accessibility, comprehensive forensic collection and signed/cross-version distribution are unvalidated. Durable artifacts/quarantine need manual retention; OS DNS/native work may outlast deadlines. These are concrete constraints, not hidden completed features.

84. **Release blockers.** No unresolved blocker remains for this controlled local Phase 8 acceptance/package scope. Production release claims for the unvalidated providers/devices/installer/accessibility/endurance areas above remain blocked until their prerequisites and tests exist. Frozen GUI startup works without Python on PATH, but Builder compilation still needs a suitable external project toolchain. Missing models/providers remain visibly degraded. The local executable is not represented as a universal turnkey release.

85. **Experimental features.** Scoped defensive heuristics, arbitrary semantic vision/provider adapters, physical cross-platform mesh operation and unvalidated Builder stacks remain experimental or unavailable where documented. Controlled PCM voice metrics are fixtures. Model explanatory text is not verified science. No image/video generator, new model/download pipeline or offensive security feature was added.

86. **Phase 9 readiness.** Ready for the user's Phase 9 prompt on the same shared systems. Existing node-scoped GPU/VRAM/RAM descriptors, bounded workers, verification, permissions, cancellation and owned-model unload hooks support extension. Phase 9 must account for actual cached model residency/live VRAM/offload before allocation, enforce the demonstrated 4.5+3.5 GiB/6 GiB admission limit and preserve direct/UI responsiveness. Readiness does not mean media generation is implemented; Phase 9 has not started.
