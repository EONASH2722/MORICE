# Phase 5 Device Mesh report

Repository: `E:\MORICE`, Windows, Python 3.14.2 in the repository environment. **Phase 5 is implemented and validated for the Windows/full-protocol node contracts, with concrete platform/provider constraints documented below. Ready for the user's Phase 6 prompt.** Full regression passed 776 tests and 59 subtests; the final related selection passed 208 tests after the stream-lifecycle repairs. [Developer guide](device-mesh.md) and [security review](device-mesh-audit.md) describe deployment boundaries.

1. **Phase 1 foundation.** CapabilityKernel, Registry, typed results, PermissionManager, ResourceManager, events and telemetry remain authoritative. Provider lookup adds optional node scope while local lookup remains the default.

2. **Phase 2 foundation.** Existing AgentCoordinator, TaskGraph, WorkerManager, SharedTaskState, nine roles, checkpoints, model budget and bounded pools remain. There is no RemoteAgentRuntime or duplicate orchestration.

3. **Phase 3 foundation.** Existing desired-state bindings, observation, verification, bounded recovery, journal and history remain. Remote providers register node-scoped bindings; local observation contracts retain their path.

4. **Phase 4 foundation.** Existing Project Builder sessions, source/artifact scope checks, authorize callbacks, process/runtime tests and result contracts are reused. A real verified calculator artifact reached another Kernel through the mesh.

5. **Prerequisite repairs.** Fresh prerequisite selection passed 173 tests in 87.76 s. Existing Phases 1–4 modules and actual contracts were inspected. Remote checkpoint reads now stay on their original node, source observation rechecks actual hashes, and GUI build validation waits for bounded completion before cleanup.

6. **Architecture.** DeviceMesh attaches providers and transport to the same Kernel/actions/agents. A paired Python node runs its own existing Kernel. Groups stay ordinary shared TaskGraphs; no separate task/permission/verification/history system was introduced.

7. **Transport.** TLS 1.3 with length-prefixed bounded JSON. Separate normal/pair endpoints, eight bounded RPC slots, short socket deadlines, bounded rates/backlog and no WAN relay. Desktop is LAN enabled only by user choice; standalone node defaults to loopback.

8. **Authentication/encryption.** Normal connections require mutual certificates, exact pins, matching sender identity, response request identity and unrevoked trust. Pairing verifies the full receiving pin before transmitting its code. Platform TLS supplies encryption.

9. **Pairing.** Explicit two-sided confirmation, six-digit one-use code, at most two minutes and five wrong attempts. Unknown discovery is never trust. Wrong code/pin, expiration, missing approval and replay are tested.

10. **Identity.** Stable IDs derive from existing P-256 SPKI hashes. Friendly-name/port changes preserve identity. A separately running Windows process restarted with the same identity and reconnected without re-pairing.

11. **Key storage.** Existing Windows DPAPI SecureVault protects key/trust state. Linux uses 0700/0600 local runtime state. Android uses a non-exportable Android Keystore key and existing encrypted store. Only encrypted temporary PKCS8 is used for CPython SSL loading, then removed.

12. **Revocation.** Trust is withdrawn, certificate contexts refreshed, live RPC sockets closed, peer work/source activity cancelled, pending queue entries removed and session policy reset. Explicit re-pair is tested. Completed external effects cannot be undone by revocation.

13. **Version negotiation.** Exact `morice-mesh/2` frame/descriptor compatibility is required. Unsupported versions fail closed; no fallback to v1. Legacy APIs remain compatibility-only with networking off by default.

14. **Device model.** Existing NodeDescriptor carries stable identity/platform/version. NodeState adds actual connection/capability/resource/health/latency metadata. Device metadata is data, never a planner instruction.

15. **Discovery.** Reuses existing bounded UDP LAN discovery, with a 64-entry metadata bound. Discovery cannot enroll trust. Actual multi-interface/firewall/OEM LAN behavior was not certified; manual pairing is the reliable fallback.

16. **Manual pairing.** Desktop Devices accepts host:pair-port, code and full fingerprint. The existing Android pairing activity accepts the same values and requires phone confirmation after desktop approval. Node CLI has a private local administrative channel for owner/harness confirmation.

17. **NodeRegistry.** Wraps the existing ProtectedTrustStore/TrustedNode records; persistent groups/defaults/per-capability policy are metadata. Inbound approved peers are registered for UI and bounded reconnect. Removal prunes group/default/policy references.

18. **Advertisement.** Only registered local implementations are advertised. Unavailable adapters stay unavailable. Schema/resource/status payloads are bounded and typed; dangerous remote regex validation rules are rejected. Default Python nodes expose status, calculator, Inbox and archive inspection.

19. **Routing.** Pure metadata selection uses capability, availability, grants, explicit target/default, capacity, latency, load, data locality and expensive-task battery/thermal constraints. Explicit target remains pinned; fallback requires consent in constraints. Ambiguity/sensitive automatic routing fails closed.

20. **Resources.** Existing node-scoped resource claims/reservations are reused. Scheduler admission precedes agent workers; node admission precedes command drivers. Busy nodes return failure without occupying a waiting worker. Claims cannot borrow another device's resource.

21. **Battery/load.** Routing avoids expensive work on low-battery uncharged or severely hot nodes when metrics are actually supplied. Android battery API is implemented; extra Python RAM/storage/battery measurements depend on optional psutil. GPU/VRAM are not invented. Fixture capacities test 6 GB versus 12 GB selection, not real GPU hardware.

22. **Remote execution.** Existing TaskNode/ExecutionContext and node Kernel perform authorize → lease → execute → verify. Submit ACK is not success. Stable IDs, bounded deadlines, peer ownership and completed typed evidence apply. Exact private authority tokens are not forwarded as remote blanket permission.

23. **Remote observation.** Registered independent observers query actual native state, calculation, file bytes or reviewed build data. Authenticated observe RPC returns structured state; absent fresh evidence is inconclusive. Restart observation must match the stored original intent digest.

24. **Remote verification.** Node Kernel VerificationResult plus coordinator Phase 3 desired state are required. No-op/mismatched state and missing mutation postconditions fail. Android web intent acceptance stays inconclusive because target foreground state is unobservable to the companion.

25. **Recovery.** Drop before/after execution never initiates automatic mutation replay. Existing Phase 3 reconcile observes the original command; matching desired state can be verified, otherwise review is required. Unconfirmed physical work retains coordinator leases until stopped or marked unavailable.

26. **Idempotency.** Peer-owned IDs cover capability/input/expected-state digest. Mutation intents persist before execution; changed duplicates are rejected. Completed safe reads/file ranges can be evicted within bounds; durable mutation history fails closed when full. Restart uncertainty is explicit.

27. **Cancellation.** Existing token/Kernel cancel propagates by authenticated RPC. Physical-active status controls lease release. Completed capture-start commands still cancel their owned source. Disable shares a two-second cancellation budget before closing networking. Cooperative cancellation is tested and benchmarked; uncooperative native providers retain their physical lease and require intervention.

28. **Offline behavior.** No automatic mutation queue. Explicit status-only queue is bounded to 32 entries/60 seconds, expires without execution and can be cancelled. Disable/revoke removes queued actions. Offline group branches report individual failure.

29. **Reconnect.** Five-second heartbeat driver reconnects only known paired endpoints while enabled. Address/port changes do not alter cryptographic identity. The separate Windows process restart/reconnect passed. Multi-interface network roaming remains an environmental validation gap.

30. **Heartbeat.** Runs outside the bounded agent pool. Local RPC deadlines bound individual probes; peer inactivity stops owned node activity. A six-second three-node interval recorded four heartbeat/connect RPCs and 125 ms process CPU, including activation. No ambient actions or automatic permission changes are triggered.

31. **File transfer.** Explicit dedicated Inbox, 128 KiB ranges, UUID/peer ownership, partial metadata, resume/readback, no-overwrite atomic publication and shared transfer leases. Python max 1 GiB; Android max 64 MiB. Pull reads only the remote Inbox. An interrupted partial is never complete.

32. **Integrity.** Real SHA-256 and size verify final bytes; prior ranges are re-read before resume. Different destination data, corrupt partials, malformed ranges, traversal and secret paths are rejected. Actual 1 MiB/8 MiB process-node transfers and round-trip retrieval passed.

33. **Streaming.** Optional local factories only, two sources maximum, 0.2–5 fps, 1–60 seconds and 128 KiB samples. Withdraw/disable/revoke cancel owned sources, including completed start commands; expiry detects OS permission/source withdrawal. Unreachable peers cannot confirm immediate cleanup and rely on 30-second inactivity or at-most-60-second lifetime. Persistent capture/network leases remain authoritative. No production factory or hardware throughput was fabricated.

34. **Camera.** Exact coordinator/node confirmations and real platform permission are required before a registered source starts. Denied/synthetic source cases pass. Android mesh camera capture/stream is not implemented and not advertised; camera-session/lifecycle/provider work remains.

35. **Microphone.** No default mesh microphone implementation, background capture or recording. The optional source contract requires existing mic permission and exact start authority. Real PCM/source integration and hardware/OEM validation remain required before advertising a mic provider.

36. **Screen.** No default screen/MediaProjection source. Existing local Phase 3 screen observation is retained. A remote source must obtain actual OS capture permission, supply a bounded observer and release its existing lease; Android consent/activity lifecycle remains unimplemented.

37. **Clipboard.** No default remote clipboard provider; Android background restrictions prevent treating it as available. A future adapter needs explicit permission, privacy-safe readback and real platform semantics.

38. **Notifications.** Visible Android connectivity notification is implemented for the foreground service. Cross-device notification posting/listening is not advertised; Android notification authorization and independently observed delivery remain constraints.

39. **Media.** Android volume getters/setters use actual AudioManager state, and setters compare the requested quantized level. Cross-app media-session control is not implemented in v2. The historical legacy media ACK is not mesh verification.

40. **Apps/deep links.** Android explicitly allows HTTP(S) ACTION_VIEW while MORICE is foreground. It reports intent requested but inconclusive final state. Arbitrary packages/install/deep-link state verification and accessibility privileges are not implemented.

41. **Android implementation.** Extends the existing app/service/pairing/activity/store. TLS requires Android 10+; keys stay in Keystore. Four bounded service threads/queue, rate/frame bounds, visible foreground service, stable peer grants and actual Inbox/status/volume adapters. The manifest includes normal audio-settings and network connected-device prerequisites; fresh observations downgrade changed volume/file proof. Three new instrumented cases compile but have not run. Requirements: [Android connected-device service](https://developer.android.com/develop/background-work/services/fgs/service-types#connected-device), [audio permission](https://developer.android.com/reference/android/Manifest.permission#MODIFY_AUDIO_SETTINGS).

42. **Windows implementation.** Actual standalone node process exercised normal mutual TLS, status/PID proof, deterministic calculator, capability refresh, transfers, shutdown and restart. Desktop panel/startup uses actual PySide services. No unrestricted shell or hidden camera/mic access is exposed.

43. **Linux/SBC implementation.** Same headless Python node entry point reuses Kernel/calculator/Inbox/observers without launching desktop/model/voice. No WSL/container/Linux/SBC device is available here; Linux execution and hardware are unverified. Existing package metadata still includes desktop dependencies; slim SBC packaging remains a constraint.

44. **Groups.** Persistent named groups with stable member IDs, create/update/delete and removal cleanup. Commands use the same TaskGraph, share bounded workers/resources and retain per-node verified/failed/offline results. Offline/mixed-local tests pass.

45. **UI.** Existing device button opens compact Devices with enable, trust/connection/caps/resources/health, manual pairing/explicit incoming identity review, rename/revoke, groups/defaults and per-capability policies. File quick action is hidden when unsupported/untrusted; discovery cannot rename or change peer grants. Pairing/status text is plain text. Duplicate named chat targets require a unique device. Network operations use one bounded UI worker; close waits for active operation completion.

46. **Permissions.** Same controller supports ask, deny, session, remembered and task/input-bound one-use grants. The UI's one-use quick action currently covers status; other exact actions use the capability API. Denied/OS-required policy cannot be bypassed. Withdrawal denies further access, hides prior private output and requests owned-source cleanup; unreachable/native cleanup limitations are in items 27 and 33.

47. **Privacy.** Source and Inbox sharing are explicit. Whole filesystem, contacts, messages, credentials, private folders and recordings are not automatic exports. Audit contains IDs/state, and existing action-journal redaction omits raw data/audio/frame/private-key/code fields.

48. **Prompt injection.** Remote schemas/descriptions/events cannot become instructions or authority. Event types are narrow and ignored payloads cannot approve work/change policy. Existing roles/model boundaries remain unchanged. Malicious message tests leave the node usable.

49. **Malformed input.** Tests cover duplicate/deep/invalid JSON, invalid UTF-8/numbers/frame length/version/IDs, event policy injection, provider schema and transfer input bounds. Authenticated oversized/incompatible frames reject before command admission; a valid status still runs afterward.

50. **Security audit.** Separate source and negative-case review in `device-mesh-audit.md` corrected admission, replay bounds, permission/session, checkpoint target, observer/hash, malformed metadata and lifecycle issues. It is not third-party penetration testing or remote OS attestation.

51. **Localhost protocol tests.** All 39 mesh cases passed within the final 208-test selection after the stream-lifecycle repairs. They create three independently identified real TLS nodes and real shared Kernels, with failure/cancel/recovery/transfer/group/permission/schema cases, local/OS permission withdrawal and disable cleanup, and zero sockets/streams/leases at fixture teardown.

52. **Actual Android test/absence.** No physical device appears in adb. Hardware acceleration failed because the hypervisor driver is absent; software emulation never became online. The owned emulator was stopped and Android's AVD manager removed only its verified owned state/registration. No system driver or user AVD was changed. APK compilation is the available evidence.

53. **Windows node test.** Separate actual OS process returned its real PID in the owned process family, executed verified calculator commands and exchanged hash-verified files. Restart preserved identity and reconnected without pairing. Process exit and zero remaining sockets/leases were checked.

54. **Linux/SBC test.** Explicit absence: WSL is not installed, container tooling and owned Linux/Orange Pi hardware are unavailable. No Linux result is claimed from a Windows fixture.

55. **Phase 2 workflow example.** Existing AgentCoordinator ran a real 12-command graph across two authenticated providers; group tests mix remote/local branches and an offline member, preserving partial results. No remote worker-pool replacement was introduced.

56. **Phase 3 verification example.** A handler falsely claiming a change fails against its independent unchanged observer. Original interrupted mutation state reconciles with no extra execution. Exact desired-state/file/cancellation evidence uses the same journal/binding contracts.

57. **Phase 4 project example.** A real Python addition project passed existing build/test/runtime validation, produced a verified ZIP, transferred it to another Kernel and passed actual bounded archive syntax/integrity inspection. A reviewed binding detects source changes after verification. This is inspection, not remote installation or certified app behavior.

58. **Benchmarks.** Actual separate-process measurements are in `build/phase5-benchmark.json`; graph/cancel/heartbeat/synthetic-source measurements are in `build/phase5-limits-benchmark.json`. Twelve parallel remote calculations took 513.87 ms; cooperative cancel 53.70 ms; synthetic sample 165.36 ms. Each sample identifies its provider and verifies cleanup. These are localhost samples, not WAN/mobile hardware predictions.

59. **RPC latency.** Separate-process ping median was 12.09 ms over 20 samples; capability refresh 35.71 ms, pairing 265.58 ms, small verified calculator median 133.27 ms and process restart/reconnect 2500.62 ms.

60. **Throughput.** Actual 1 MiB transfer took 1.45 s (0.690 MiB/s); 8 MiB took 10.76 s (0.744 MiB/s), with final hash proof and no resume needed in the final sample. An earlier connection drop failed closed; bounded explicit resume uses the same transfer ID, lease reconciliation and range readback. Per-chunk verification adds overhead. Larger maximums are input bounds, not a measured 1 GiB claim.

61. **Idle CPU/RAM.** Native OS process measurements showed 0% one-core CPU over the sampled idle interval and 106.44 MiB working set for the compute node. Optional psutil is not needed by the benchmark. Memory includes existing scientific dependencies; this is not a tiny embedded firmware footprint.

62. **Startup/performance.** Actual services/main-window/empty Devices initialized, with lazy mesh/agent/builder, 60 initial capabilities/nine roles, zero critical health failures and zero disabled listeners. Latest startup: 179.74 ms constructor/1203.50 ms total; local direct echo median 0.316 ms over 250 calls, with no agent/network dispatch. This is higher than the earlier Phase 4 sample (~0.275 ms); host conditions differ and no controlled regression attribution is claimed. Single samples cannot prove statistical no regression.

63. **Tests added.** 39 Python mesh cases, two Project Builder integration cases and three compiled Android instrumented cases. Existing GUI completion wait was corrected without removing behavioral/file assertions. Android cases are unexecuted, not three passing tests.

64. **Targeted results.** Final foundation/mesh/action/project selection passed 208 tests in 120.83 s after the stream-lifecycle repairs. The isolated project environment recheck passed in 15.85 s; its earlier deadline-cancelled run is retained as failed evidence. Two focused Project Builder cases passed in 12.37 s and the corrected GUI case passed in 18.14 s.

65. **Complete regression.** 776 passed, 59 subtests passed, 1222.01 s, in `build/phase5-full-tests.log`. The subsequent cancellation-budget refinement was checked by the related selection plus actual startup. Initial full run had one eight-second GUI cleanup race; it was corrected and rechecked, not counted as a passing run. A separate targeted run had a deadline cancellation during local Python environment creation (207 passed/one failed); the unchanged case then passed in isolation in 15.85 s. That failed run remains recorded in `build/phase5-targeted-timeout.log`.

66. **Startup health.** Zero critical failures, actual window/Devices initialization, shared Kernel identity, networking off by default, lazy pools/builder and no remote peers. Startup evidence is `build/phase5-startup.json`; shutdown checks zero leases/sockets.

67. **Packaging.** Local wheel has 55 source-equal shared/mesh runtime modules, including all 13 mesh modules, plus four source-equal modified entrypoint modules. ZIP integrity is valid; SHA-256 `335e70301b92c1490355549b314f960f37881d97bc18348e0ea703d0414a21e5` (1,992,040 bytes). Android debug/instrumentation builds succeeded after the manifest/fresh-observation repairs; hashes/sizes are in `build/phase5-package.json`. Frozen spec collects mesh modules; no portable executable/public binary release is claimed.

68. **Remaining limitations.** Unverified Android/Linux/SBC execution, OEM/LAN roaming, absent default hardware captures/media/clipboard/location/install/shell providers, no slim SBC package, bounded durable mutation ledger, five-year certificate rotation, persisted partial wall-clock expiry, no hostile-code sandbox/remote attestation and cooperative native source teardown. Phases 3–4 provider constraints remain as recorded below; no missing provider is advertised as working.

69. **Files added.** Thirteen `morice/device_mesh/*.py` modules; Android MeshIdentity/MeshClient/MeshNode/MeshJson and MeshInstrumentedTest; `tests/test_device_mesh.py`; benchmark_device_mesh, benchmark_device_mesh_limits, verify_mesh_startup and verify_mesh_package scripts; this report, guide and audit.

70. **Files modified.** Existing Kernel registry/execution/scheduler/adapters; Phase 2 coordinator/workers/planner/roles; Phase 3 runtime/journal; ProjectBuildRuntime delivery; node_protocol descriptor; RuntimeServices/settings/PySide Devices/natural target routing; AndroidManifest.xml and four existing Android Java activity/service/store files; MORICE.spec; Project Builder tests and GUI completion wait. Prior user edits/deleted screenshots are preserved. Nothing was committed/pushed/published.

71. **Phase 6 readiness.** The existing researcher/analyst/simulation/verifier roles can use node-scoped computation and genuine registered input providers. Verified source artifacts/files and observations retain the common evidence contracts. No new laboratory/research ecosystem or model download was introduced; unsupported hardware/providers remain unavailable.

72. **Phase 7 readiness.** Stable authorized identities, concrete desired states, observe-before-retry, bounded queues/cancel/recovery and groups form an integration base. Broader autonomy cannot assume hostile-code isolation, universal UI observation or unvalidated remote hardware.

73. **Phase 8 readiness.** Typed node health/resource/evidence, groups/defaults, compact Devices and explicit failure metadata are available for later integration. No Phase 8 implementation or product-mode expansion was started.

74. **Phase 9 readiness.** Local wheel/APK build and reproducible tests/benchmarks are available. Release signing, real device/platform certification, certificate maintenance and production packaging remain review work. No commit, push, merge, tag, release, deployment, upload or public website change was performed.

## The five explicit Phase 2 limitations

| Target | Current integration status and remaining technical constraint |
|---|---|
| Search snippets versus verified browsing | Phase 3 actual embedded navigation/DOM/tabs/downloads is retained and regressed. Search snippets remain unverified; external browsers, cross-frame/shadow DOM, authenticated challenges and picker uploads remain outside implemented provider coverage. |
| Limited semantic vision | Existing accessibility/semantic DOM and structured screen observations are retained. Universal full semantic pixel understanding is not implemented; an actually configured backend/provider is still required. No mesh device advertisement invents semantic vision or captures. |
| Desktop observe/recover loop | Existing Phase 3 desired-state observe/verify/bounded alternatives/reconcile/journal is retained and extended to remote observations. Universal UIA/OEM behavior, arbitrary external rollback and noncooperative native providers remain constraints. |
| Resource waits consuming workers | Existing scheduler reserves before agent workers; Phase 5 additionally reserves physical node resources before command drivers. Heartbeat/discovery/reconnect/queue expiry stay outside the agent pool. Active real remote work/short RPC polling still occupies its assigned worker; the underlying direct Kernel may wait for resources outside admitted paths. |
| Small parallel tasks slower | Local simple actions still dispatch directly with networking/pools lazy. Remote distribution deliberately adds TLS/observation cost; metadata routing is explicit. Benchmark samples separate direct echo from remote verified calculation rather than claiming parallel execution accelerates trivial commands. |
