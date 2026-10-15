# Phase 3 foundation audit

The live Phase 1 kernel and Phase 2 coordinator were inspected before Phase 3 changes. Their registry, task graph, worker manager, shared task state, permissions, cancellation, verification contracts, and node-scoped resource leases are present. The foundation regression run passed 123 tests and 14 subtests (9.18 seconds); output is in `build/phase3-foundation-tests.log`.

Concrete gaps found:

- The system-browser controller cached the requested URL and exposed it as observed navigation. A launch acknowledgement could therefore become a false positive.
- Application launch verification accepted a running process without a usable window for several launch types. Opening an already running application could launch another instance.
- File opening checked file existence, which proves neither viewer launch nor document display.
- Desktop providers contain fixed polling loops without the kernel cancellation token.
- The parallel scheduler dispatched resource contenders into bounded worker slots before waiting for leases.
- Search snippets and image metadata do not establish browser navigation or semantic screen understanding.

Phase 3 extends the existing execution boundary and scheduler. Deterministic PC actions continue through the fast router and kernel, without creating agent workers. The existing permission authorities, task statuses, verification results, resource manager, process cancellation, and patch undo store remain authoritative.

## Final implementation audit — 2026-10-04

The final full regression run passed **697 tests and 59 subtests in 181.12 seconds**. The 54 new Phase 3 cases include a fresh-process integration test that uses the actual Qt browser, local HTTP server, downloaded bytes, subprocesses, and visible Win32 windows. These are controlled local fixtures; they do not establish compatibility with every third-party application or website.

Repairs and verification:

- Requested system-browser URLs no longer masquerade as observed URLs. The embedded browser supplies current URL, load completion, DOM facts, and page generation. A real wrong redirect fails verification.
- Win32 observations include process image, process family, window handle, geometry, visibility, enabled state, DPI, and monitor. Process existence alone cannot establish application readiness. Title-only matches cannot select an unrelated application.
- Windows virtual-environment process launch can return a redirector PID instead of the visible application PID. Actual child process identity is now followed; the real viewer demo verifies that family rather than assuming identical PIDs.
- Already usable application windows satisfy idempotent open actions without launching another copy. Minimized windows require restoration. Ambiguous matches and save dialogs require user intervention.
- File open requires an independently associated viewer/document and exactly one visible, enabled, non-minimized window with positive bounds; existing file bytes alone cannot make it succeed. The owned viewer fixture demonstrates this association. A final fault test rejects hidden, minimized, disabled, zero-size, unowned, and ambiguous viewers. Ordinary shell associations remain inconclusive when they expose no usable identity.
- Patch verification reads the actual resulting bytes and hashes. Undo reads the existing manifest and independently checks restored or removed files. Build/test verification uses the owned process's actual exit code, cancellation state, and captured output.
- Resource admission now reserves existing claims before dispatching Phase 2 workers. A busy foreground task remains pending while an independent I/O task can use the free worker. Reservations pass through the existing WorkerManager context and are released by actual work.
- Project build resource claims are added before coordinator fingerprinting. This prevents legitimate runtime preparation from invalidating an approved graph.
- Browser work crosses Qt signals to the existing UI thread. Callbacks explicitly serialize DOM values because this PySide build did not reliably return JavaScript objects as Python dictionaries. Late, cancelled, or superseded callbacks cannot authorize another action.
- Browser tabs use owned QWebEnginePage instances. The implicit Qt page's deletion on page switching is accounted for. Shared-profile download signals ignore pages owned by another MORICE window.
- Generic browser click, submit, and upload require exact permission confirmation. Search queries retain the Phase 2 query schema and the PC permission broker; broader native grants cannot bypass a broker denial. Search snippets remain unverified source evidence.
- Interrupted checkpoint recovery observes current state once under fresh read permission and available resource claims. It does not replay mutations or reuse an old approval token.
- Journal intent is durable before mutation. Root cancellation seals the original execution attempt even when an inline observer raises; detached callbacks cannot replace that final outcome.

## Exact Phase 2 limitations

| Original limitation | Phase 3 result | Concrete remaining constraint |
| --- | --- | --- |
| Web relies on snippets | Resolved for the existing embedded Qt browser: verified navigation, DOM interaction, tab control, extraction, and downloads | The system browser has no DOM provider. Login, OTP, CAPTCHA, upload picker automation, cross-frame/shadow DOM, and browser extensions are not implemented. |
| Vision gives metadata | Optional semantic screen observer now reuses LiveVision, checks screenshot/frame identity, and caches repeated frames | A compatible local vision model/projector is not configured. No real model inference was validated. Semantic output is a hypothesis and never independently establishes action success. |
| No desktop observe/recover loop | Real Win32 execute/observe/verify and bounded alternative-capability recovery are implemented and exercised | Full Windows UI Automation and generic mouse/keyboard providers are absent. Store-app wrapper windows and unidentifiable shell viewers can remain inconclusive. |
| Resource waits occupy workers | Normal DAG resource contenders wait in scheduler admission, outside the task worker pool | Direct kernel calls and a retry that needs different resources still use the existing cancellable kernel wait. Observing a running action uses its worker for a bounded interval. Uncooperative native work retains its lease until it actually exits. |
| Small tasks have parallel overhead | Deterministic PC routing remains ahead of agent planning; benchmark dispatches zero agents | Durable mutation journaling and read-back verification add measurable latency: roughly 12 ms per patch and 14 ms per short test process on this machine. |

The UI Automation package is not installed and no new model was downloaded. Missing providers are surfaced as unavailable, blocked, or inconclusive rather than replaced with fabricated evidence. BASIC, NORMAL, STRICT, and DOMAIN_SPECIFIC currently share the minimum domain proof; they do not claim distinct application-specific assurance. NONE cannot certify a mutable action.

## Validation boundaries

The final full suite took 181.12 seconds; its slowest tests were existing large-project knowledge retrieval (23.89 seconds), existing GPU-fit planning (13.01 seconds), and the new real browser integration (12.59 seconds). The preceding profiled run passed 696 tests in 104.58 seconds before the final viewer fix. A previous successful run reported 4198.27 seconds without duration profiling. That anomaly was not reproduced and its cause is not established. These variable full-suite wall times are not a controlled performance comparison; the isolated paired action benchmark supplies the latency measurements.

Local startup reports 60 capabilities, nine production roles, the same shared kernel, an attached embedded-browser bridge, zero critical failures, lazy agent pools, and zero remaining leases. The locally built wheel contains all 32 kernel/agent/action modules with exact source-byte matches. No commit, push, release, deployment, upload, or public website change was performed.

See `verified-action-runtime.md` for integration and `verified-action-runtime-report.md` for the required 46-item completion report. Raw evidence is under `build/phase3-*`.
