# Phase 8 separate source and security review

This review revisited the existing authorities, failure paths and final implementation after the main integration work. It is a separate inspection and fault-injection pass by the implementing agent, not independent human review or a third-party security certification. The full results and artifact locations appear in [full-stack-hardening-report.md](full-stack-hardening-report.md).

## Findings repaired

| Finding | Concrete consequence | Final behavior and evidence |
|---|---|---|
| Event callbacks ran while holding the bus lock | A subscriber waiting on a domain lock could deadlock another publisher that held that domain lock | Single bounded FIFO drainer releases the bus lock before callbacks; controlled lock-inversion and concurrent flood tests pass |
| Raw subscriber, handler and crash exceptions reached diagnostics | Controlled credential canaries appeared in logs or persisted diagnostic state | Shared bounded redaction, typed callback errors, useful redacted handler errors and crash stacks; nested/Bearer/environment/rotation cases pass |
| Bad action journal could become an empty journal | Restart could discard interrupted action evidence | Preserve bytes, expose `load_error`, block mutations and reconciliation pending review, keep unrelated direct reads available |
| Checkpoint encoding could race shared state | A partially changing graph could serialize inconsistent evidence | Existing lock covers JSON encoding; bounded, flushed, atomic checkpoint replacement and strict restore validation |
| Research terminal status preceded control cleanup | Immediate resume could see an old active worker and lose the request | Terminal status is visible only after the laboratory control acknowledges completion; actual pause/cancel/resume tests and full regressions pass |
| Optional telemetry could construct another runtime | UI helpers could open an unrelated profile or task manager | Nonactivating `peek_runtime_services()` and explicit UI runtime injection |
| Health checks imported optional native providers eagerly | Startup initialized unnecessary services and could fail when unrelated providers were absent | Metadata/spec availability check; native initialization remains on demand; optional missing dependency is degraded |
| A suspended stream left a caller context marker | A second independent chat stream could borrow the first stream's model reservation | Generator keeps its real lease without leaving a caller-thread execution scope; busy second stream is rejected and generator close releases ownership |
| Resource scope checked only the resource name | A remote-node model claim could be mistaken for admission of local model work | `current_holds()` checks node identity; remote scope plus a busy local model cannot invoke the local backend |
| Diagnostic recursion rescanned environment credentials per string | Security hardening added avoidable fast-path overhead | One fresh environment snapshot per redacted record; no persistent cache that misses newly rotated credentials |
| Provider malformed JSON retained connected status | Failed reads could coexist with misleading connected diagnostics | Transport/schema failures set a truthful degraded/unavailable state; no successful verification without observed provider objects |
| Network-unavailable capability could never probe after cache refresh | A temporary outage remained stuck even after service recovery | Actual outage reproduction failed before repair; degraded admission permits a later authorized probe, while a 60-second retry time prevents immediate repeated network work |
| Late HTTP errors could overwrite disconnect state | A transport error after account disconnect could obscure its disabled/auth state | Provider generation checks and registry terminal-state preservation; existing disconnect/cancellation tests plus actual chaos regressions |
| Shutdown marked clean with retained physical work | Dirty restart could be suppressed even though an operation continued | Admission closes before cleanup, no callbacks under the runtime lock, actual remaining leases/pending workers determine the shutdown result |
| Windows `psutil.disk_usage(Path)` broke mesh hello metadata | Optional profiling dependency caused a full protocol handshake failure | Pass an actual path string; optional metadata failure degrades rather than killing hello |
| Frozen spec implicitly required/embedded GGUF | Packaging failed without developer weights or embedded a multi-gigabyte local model unintentionally | Default external model assets, explicit existing model-bundle opt-in, core package collection and clean-profile degraded chat |
| Packaging probe omitted explicit UI health | A successful window probe had an empty health list | Actual startup health is invoked and must be recorded; earlier empty-health probe is superseded |

The reproduction, first failed full run, unsuccessful harness runs and corrected evidence remain available. Test fixtures were corrected when they assumed host battery charging, omitted required DOM regions, used an obsolete background-task callback signature or checked a live uncertainty lease as though it were a leak. Those changes do not weaken production verification. The native interaction fixture's first route assertion used the wrong `ControlAction` field; that run is recorded as a harness failure, not a verified native action.

## Authority and boundary review

The AST inventory has 166 modules, one expected definition per execution authority, no multi-module top-level import cycle and four function-scope cycle groups. Large preexisting UI modules remain. The renderer artifact cache shares the class name `ResourceManager` but has no scheduling authority. There is no new scheduler or agent pool hidden in the hardening helpers.

Permissions continue through existing kernel and domain providers. Denial wins, one-use grants bind the exact task/action/arguments, and no journal or diagnostic includes reusable approval tokens. A model lease is not a permission grant. Untrusted provider/document text cannot choose authorized consequences. Browser search snippets remain evidence of search results, not proof of browser navigation. Real browser success requires DOM/screenshot observation and the configured verification contract.

Existing filesystem/Builder/mesh/security tests cover scoped paths, path traversal, hashes, partial transfers, links/reparse paths, overwrite refusal, malformed bounded messages, replay, revocation and encrypted evidence. Actual crash recovery kills an owned child after a real file mutation and verifies the file after restart without invoking the mutating handler again. Corrupt action/checkpoint bytes are preserved. Interrupted SQLite transactions roll back existing records. No destructive repair is used to manufacture a clean result.

Connector chaos uses real loopback HTTP for 401, 403, 429, 500, delayed response, reset connection, invalid JSON and refused connection. The same kernel permission and verification boundary rejects each failed read, releases leases, avoids sleeping cooldown workers and verifies recovery after a forced health refresh. OAuth/signatures/refresh/replay/revocation have preceding-phase regression coverage; these fixtures do not replace real production authorization testing.

Secrets are assessed with synthetic canaries and encrypted fixture vault data. No real credential is printed for audit. Redaction is conservative pattern-based protection; unknown unlabeled private content and arbitrary external subprocess output require continued care. No credentials, personal settings, journals or model weights appear in the default release archives. There is no claim of an exhaustive vulnerability database scan.

## Evidence limits and release constraints

Local source and archive parity, controlled Windows integration, CUDA model execution, actual owned processes/files/SQLite, Qt Chromium observations and mutually authenticated loopback nodes are validated. All production provider accounts and physical cross-platform devices remain outside the measured scope.

Frozen startup is materially slower than source startup. Baseline startup includes a large first-run outlier and sequential measurements affected by filesystem/code caches; median changes are observations rather than a controlled attribution of every millisecond. Direct action budgets and redaction overhead are reported explicitly. Three idle runs and a 120-second steady-state soak cannot establish long-term leak freedom or MTBF. GPU samples include other host allocations.

Voice ordering/barge-in tests use a controlled provider and sink; microphone/wake quality, cloud TTS response time and physical audible output remain unvalidated. Semantic vision requires a configured available provider. Full Android/Linux, production GitHub OAuth/HTTPS relay, signed installer distribution, formal accessibility and comprehensive defensive security forensics remain release constraints. Large UI classes and manual artifact/quarantine retention remain maintenance constraints.

An uncooperative native/DNS operation may exceed the request's deadline. Physical ownership is retained and shutdown is reported dirty instead of claiming forced termination. SQLite corruption has no automatic destructive repair. Connector polling, event dedupe and webhook replay ledgers have finite retention; old windows require explicit operational review.

Phase 9 can extend the validated shared admission and unload contracts, but must add physical model-residency accounting and live VRAM/offload checks before actual generator allocation. Cached LLM weights remain in VRAM after request leases end. The synthetic 4.5 GiB + 3.5 GiB/6 GiB test proves lease admission only; it does not prove that media models run on this hardware. No Phase 9 generation pipeline was started.
