# Revised Phase 10 acceptance report

Current acceptance, 2026-10-15: **1,077 tests and 62 subtests pass in 398.39 seconds**. Matching native wheel/frozen and installed checks pass; all twelve themes visibly animate, the composer stays inside the screen and navigation appears once. Native cached vector curves have closed position/velocity cycles. [Final software evidence](release-audit-evidence.json) supersedes earlier global gates; measured performance and hardware/provider limits remain explicit. Historical observations below retain their original scope.


**Historical reopened gate (now superseded by the current acceptance above).** The October 14 screenshot exposed an off-screen composer during native maximize. The initial geometry checks skipped hidden controls and did not compare controls against the monitor rectangle. Current source repairs require fresh package/dist acceptance before this phase is marked complete again. This report follows the 102 requested topics and retains the prior evidence as history. No public release, push or website deployment has occurred.

The current correction adds a visible editor after reparenting, a route stack whose hidden pages cannot impose a height-for-width constraint on the window, and required composer/Send checks against both window and usable screen rectangles. On the native 1.25-DPR monitor the bad maximize reached 1536×1376 logical pixels on a 1536×864 usable screen; the corrected native maximize stays at 1536×864 and restores to 1366×840. `build/theme-composer-native/evidence.json` and the reproduction logs retain the evidence.

Every preset now owns a distinct authored scene and animation; Glass is a named, discoverable option with translucent application surfaces, cached procedural refraction and reflective edges. Scene paths and particle trajectories have matching position and velocity at the cycle boundary. LOW quality retains four inexpensive ambient layers at four raster updates per second; explicit Reduced Motion, hidden/minimized windows and high contrast retain their controls. A top-bar Theme menu makes theme selection and animation enablement reachable. The focused correction selection passes 110 tests; new final full-suite and package gates are running.

The earlier clean full regression passed **1,054 tests and 62 subtests**. The final UI/timer selection passed **140 tests**. Final-source wheel/frozen parity and outside-checkout native startup now pass. The subsequent full run exposed controlled-fixture/live-RAM inconsistency (20 failures) and a Windows launch of placeholder executable bytes; both test fixtures were repaired without changing application source or guards. All 66 other platform/Media cases and the corrected relaunch case pass. The final complete rerun passed **1,058 tests and 62 subtests in 463.62 seconds**. Both installed launch paths now pass native startup, with 78/79 UI ticks, zero critical failures/leases/workers and clean shutdown. The prior build and three local GGUF files are retained. No public action has occurred.

## Evidence and limits

The native captures in `build/phase10-production-preview-v2` cover all 17 routes and were visually reviewed as a contact sheet. The first 13-case native geometry matrix passed, then visual review found and repaired the large-text category width; the final native category recheck passed with zero issues and was visually reviewed. These are captures of the owned Qt application, not another app or synthetic product mockups.

`build/phase10-master-workspace/272d913337/evidence.json` records a fresh 10,000-run deterministic Research sweep with actual partial progress, explicit pause/resume, zero model calls and a 500-row display bound; a Builder result verified by its real commands/tests; a 1,048,832-byte mutually authenticated localhost TLS transfer with a matching received hash; and decoding of the actual previously verified Phase 9 image. The ideal-mixture calculations are computations, not laboratory measurements. This run predates only the category-layout and final timer-lifetime repairs.

`build/phase10-production-wake-spatial` records actual Vosk recognition and Windows SAPI replies through bounded memory audio transports. The physical microphone/speaker is not certified. Six complete, non-aborted replies preserve the existing confidence threshold, geography, units and context replacement. The lower-confidence wake samples were rejected.

`build/phase10-production-cinematic` contains a clearly labelled fifteen-state visual fixture and separately real Phase 2 coordinator, deterministic command, Spatial, cursor and policy checks. The gallery is not proof of fifteen live jobs. Native quality probing reached LOW/BALANCED/HIGH/ULTRA on this run; quality selection was not forced past real power/focus policy.

`build/phase10-matched-native-benchmark.json` alternates three native source samples per constructor using isolated profiles and no models. Median first-ready time: legacy 4,714.08 ms; renovation 5,573.85 ms. Reduced-motion idle: legacy 373.66 MiB / 0.12% total CPU; renovation 390.61 MiB / 0.14% total CPU. The retained legacy constructor uses current controllers, not historical release bytes. The device-wide GPU snapshot includes other processes; per-app graphics GPU use, compositor latency and per-app VRAM are unmeasured.

`build/phase10-production-soak/evidence.json` records 301.12 seconds, 196 route/theme cycles, actual coordinator work, repeated wake/child-window lifetimes, zero remaining leases/workers and returning widget counts. Scheduling median 21.12 ms, p95 25.30 ms, worst 2,309.22 ms includes synchronous window construction/theme work and CPU load. This is not a compositor benchmark. This run exposed a late clock rearm after close; the repair has a regression test and a stronger follow-up soak assertion. The 121.42-second follow-up completed 76 cycles with a closed/inactive clock, zero remaining subscribers and clean shutdown; scheduling p95 45.91 ms, worst 3,976.89 ms. The final all-route timer audit also found and repaired a retained wake poller; it now reports zero active UI timers after close. The parent window listener remains active. Retained synchronous controller construction remains a measurable startup/child-window cost.

`build/phase10-security-load-current/evidence.json` records an actual Security scan of an explicitly scoped harmless fixture, a real high-severity stored finding/Core alert, ignore/disable and notice expiry. The existing resource manager's actual controlled GPU lease reduces ULTRA to BALANCED and restores ULTRA on release. This validates lease adaptation, not a new heavy model/GPU generation run.

The accepted Phase 9 RAM constraint remains in force. No new heavy generation, video model, cloud provider, physical phone, physical monitor removal, microphone/speaker or per-app GPU attribution is claimed. No resource margin, wake confidence threshold, permissions or verification authority was lowered.

## Requested topics

The five explicit Phase 2 integration targets remain tracked in item 40 of `verified-action-runtime-report.md`: verified embedded browser navigation/DOM/tabs/downloads exist, while external/shadow/frame/authentication cases and snippet verification remain limited; semantic vision requires a configured compatible provider and cannot certify an action from metadata; Win32 observe/recovery is bounded to identifiable processes/windows and lacks general UI Automation; normal parallel contention waits before worker submission, while direct/retry/uncooperative native cases retain documented waits/leases; deterministic actions continue bypassing agent execution. Renovation reuses those same authorities. New Media UI submission returns the existing scheduler identifier instead of occupying a general worker through resource waits.

| # | Topic | Result / concrete evidence |
| --- | --- | --- |
| 1 | Phase 1Ã¢â‚¬â€œ9 status | Existing systems retained; full regression covers their contracts. Existing provider/hardware constraints remain explicit. |
| 2 | Prerequisite repairs | UI encoder discovery, export enum/message, queued speech, rich HTML scope/theme, category fit and late clock rearm were reproduced and repaired. |
| 3 | Old UI audit | Classified final-source audit preserves 265 controller methods, mounts 81 named controls and accounts for all 15 replacements. |
| 4 | Parity matrix | `renovation-parity-matrix.md` tracks each group and remaining evidence. |
| 5 | New UI architecture | One production factory, one existing runtime, queued bounded presentation adapters. |
| 6 | MORICE Core | Original procedural luminous point/orbits; no eyes, face or copied video. |
| 7 | Core state machine | Fifteen public states; bounded event maps, aggregate workflow outcome, actual input/output RMS. |
| 8 | Energy-field renderer | Cached bounded raster field; original curves/particles, no prerecorded video. |
| 9 | Energy state behavior | Actual Core state colors; labelled gallery separated from real coordinator/Security evidence. |
| 10 | Performance quality levels | LOW/BALANCED/HIGH/ULTRA native paint/raster/CPU samples recorded. |
| 11 | Load-aware visual scaling | Existing leases, GPU metrics, power/focus and media events control the same policy. |
| 12 | Design token system | Data-only semantic colors, surfaces, typography, spacing and control sizes. |
| 13 | Theme engine | Strict bounded schema and crash-safe preferences; no executable imported theme data. |
| 14 | Default MORICE theme | Deep blue/violet surfaces, restrained cyan focus and luminous Core. |
| 15 | Theme customization | Twelve distinct scene presets including Glass; validated accent/surface/font/motion/field settings. |
| 16 | Appearance Lab | Searchable simple/advanced controls; live preview, import/export/reset. |
| 17 | Cursor-field interaction | Owned Qt pointer delivery, bounded localized field reaction. |
| 18 | Cursor lighting | Nearest visible control lighting, actual pointer preserved. |
| 19 | Cursor glow | Bounded trail/pulse, minimal/disabled choices and reduced-motion behavior. |
| 20 | Magnetic controls | Authored decorative response preserves stable actual hit areas. |
| 21 | Glass/material system | Central token surfaces; high contrast and effects-off remain usable. |
| 22 | Motion engine | One weak-subscriber visible-only clock; finite bounded transitions; closed clock cannot rearm. |
| 23 | Transition system | Interrupted transitions finish safely; reduced-motion final geometry is tested. |
| 24 | Sidebar/navigation | Compact rail, accessible named custom icons, expandable labels and palette. |
| 25 | Core Home | Calm central field/Core, contextual composer and action deck. |
| 26 | Bottom action deck | Seven stable authored icon actions, hover/focus labels and keyboard access. |
| 27 | Edge telemetry | Public status only; actual tasks/health, no private reasoning. |
| 28 | Chat redesign | Retained realtime stream/cancel controller inside the new presentation. |
| 29 | Composer | Compact content-responsive input with Attach/Voice and expandable context. |
| 30 | Response cards | Existing streaming/math/code/artifact rendering; six native rich-theme cases pass. |
| 31 | Activity Center | Actual bounded task/event records, prompt queue and cancellation. |
| 32 | Agent visualization | Same Phase 2 role/coordinator/task events; no invented role nodes or progress. |
| 33 | Voice integration | Existing STT/TTS/permissions, exactly-once speech and public RMS. |
| 34 | Wake architecture | Existing listener/handoff/speech owners; epoch, stale result and timeout contracts. |
| 35 | Wake orb | Compact Core-based overlay with strict bounded preferences. |
| 36 | Wake transitions | Actual minimized owned window Ã¢â€ â€™ wake Ã¢â€ â€™ Spatial recognition run. |
| 37 | Barge-in | Existing cancellation/echo/stale-token tests; physical audio remains unverified. |
| 38 | Builder redesign | Existing forms/review/terminal in Projects; real owned build/tests verified. |
| 39 | Research redesign | Existing laboratory store/experiment manager, nonblocking bounded presentation reads. |
| 40 | Research knowledge visualization | Stored provenance/relationship graph; at most 200 displayed nodes, no inferred evidence. |
| 41 | Experiments | Actual 10,000-run sweep; explicit pause/resume, persisted results and 500 display rows. |
| 42 | Simulation rendering | Existing meaningful physics/renderer clocks retained; hidden presentation polling stops. |
| 43 | Spatial architecture | Domain extension registered in the existing Kernel, no second executor. |
| 44 | Geocoder | Offline GeoNames 34,154-city data, exact aliases and explicit ambiguity selection. |
| 45 | Earth model | WGS84, provenance-tagged deterministic math and Natural Earth land data. |
| 46 | Geodesic distance | GeographicLib WGS84; ChennaiÃ¢â‚¬â€œLos Angeles 14,433.880849560375 km. |
| 47 | Chord distance | WGS84 ECEF Euclidean chord; separately labelled through-Earth distance. |
| 48 | Routing integration | Route unavailable without a configured real route provider; no invented roads. |
| 49 | Bearings | Deterministic initial/final bearings and geographic edge-case tests. |
| 50 | Multi-point path | Typed bounded path/area/radius contracts and tests. |
| 51 | Globe rendering | Interactive bounded orthographic projection and inverse selection. |
| 52 | 2D map | Equirectangular projection with dateline segmentation. |
| 53 | Spatial voice context | Units/mode/replacement retained across actual recognized commands. |
| 54 | Wake Ã¢â€ â€™ Spatial flow | Six real recognized commands and complete local PCM speech replies. |
| 55 | Device Mesh redesign | Existing pairing/trust/policies/actions in Devices; no automatic pairing. |
| 56 | Device topology | Existing node/group metadata and actual connection state; no fake physical phone. |
| 57 | File-transfer UI | Actual owned localhost TLS transfer with verified bytes/hash. |
| 58 | Media Lab redesign | Generate/edit/queue/history/models, typed profiles and explicit availability. |
| 59 | Media generation UI | Real verified Phase 9 PNG loaded; fresh heavy generation constrained by accepted RAM margin. |
| 60 | Load-aware GPU behavior | Actual controlled lease and public media/GPU events; physical new generation unmeasured. |
| 61 | Automations redesign | Existing opted-in watch/run/confirmation authority, new route. |
| 62 | Connectors redesign | Existing registry/vault/authorization/fault contracts; no production OAuth success claim. |
| 63 | Security redesign | Existing scoped monitor/finding/incident/defensive actions in Security. |
| 64 | Security Core state | Actual harmless known-hash finding triggers alert; ignore/disable and notice expiry verified. |
| 65 | History redesign | Search/reopen/name/protect/archive/delete retained; new persistent route does not hide itself on reopen. |
| 66 | Settings redesign | Searchable categories and existing preference authority; large-text category fit repaired. |
| 67 | Command palette | Existing commands plus all routes/themes, same permission checks. |
| 68 | Notifications | Existing notification authority/public status routed into the new shell. |
| 69 | Reduced Motion | Static orbits/field/particles, simplified transitions, meaningful physics retained. |
| 70 | Accessibility | Named controls, custom chevrons/focus, contrast tests, keyboard and large text. |
| 71 | DPI | Thirteen owned native cases and corrected 1.8-scale category capture pass; native captures reviewed. |
| 72 | Multi-monitor | Logical backing/geometry tested; physical monitor removal is unverified. |
| 73 | Resize behavior | Composer bounds/fit/overlap checked, compact settings names elide with full tooltips. |
| 74 | Theme stress | Preset swaps in focus tests/native six-rich-theme cases and repeated soak. |
| 75 | Cursor stress | Bounded target/trail tests and owned Qt pointer sample; no native pointer replacement. |
| 76 | Animation stress | Interrupted/reduced-motion/bounded clock tests and route/theme/child soak. |
| 77 | Memory soak | 301-second load/route soak plus 121-second closure follow-up; returning widget counts and bounded owners. Scheduling outliers remain explicit. |
| 78 | Timer cleanup | Closed-guard regression/follow-up soak pass; final all-route audit reports zero active UI timers. |
| 79 | Logo quality improvement | Same high-resolution bitmap rendered with actual DPI/smooth scaling; all eight 16â€“512 pixel sizes reviewed; identity unchanged. |
| 80 | Proof logo identity unchanged | PNG SHA256 `76a2a5e23aba67a785e9234a05be8c7fa9982c5fda4f0a09d5396a0f3c40bc2a`, byte-identical to original HEAD. |
| 81 | Benchmark startup | Matched median 5.57 s renovation / 4.71 s retained legacy source; constructor cost remains. |
| 82 | Benchmark idle CPU | Reduced-motion median 0.14% total CPU renovation; quality-specific one-core CPU recorded separately. |
| 83 | Benchmark idle RAM | Reduced-motion median 390.61 MiB renovation, 373.66 MiB retained legacy. |
| 84 | Benchmark idle GPU | Device-wide snapshot only; per-app graphics utilization is unmeasured. |
| 85 | VRAM use | Device aggregate available; per-app compositor VRAM and fresh generation attribution unmeasured. |
| 86 | Frame-time results | Paint/raster CPU and event scheduling median/p95/worst recorded separately; no compositor claim. |
| 87 | Spatial performance | Actual native view, geographic computations and bounded redraw tests. |
| 88 | Media coexistence | Existing Media scheduler/resources/queue tests, cached diagnostics and verified image UI; heavy generation constraint retained. |
| 89 | Wake demo | `phase10-production-wake-spatial.log`: six complete replies; two lower-confidence wake samples rejected. |
| 90 | Spatial demo | Geocoder ambiguity Ã¢â€ â€™ geodesic Ã¢â€ â€™ miles Ã¢â€ â€™ chord Ã¢â€ â€™ New York replacement through actual STT. |
| 91 | Master cinematic demo | Composed actual workspace/wake/Security/coordinator/quality evidence; full physical/model end-to-end remains constrained, not certified. |
| 92 | Feature parity results | 46 matrix rows now identify migrated access and concrete contracts/constraints; all original method bindings and replacement controls accounted for. Full-suite and installed startup gates pass within the stated controlled scope. |
| 93 | Tests added | Source factory/context, orbit motion/static pixels, category fit, stream visibility and closed-clock lifetime coverage. |
| 94 | Targeted tests | Final UI/legacy focus: 140 passed. Controlled Media: 47 passed; platform+Media: 66 other cases passed, corrected relaunch case passes. |
| 95 | Full regression | Final matching source/tests: 1,058 tests + 62 subtests pass in 463.62 seconds. |
| 96 | Packaged startup | Final wheel: 214 equal modules, 17 routes. Frozen: 212 equal modules/6 assets, native startup, zero critical failures/leases/workers. Both installed EXE entry paths pass native isolated startup. |
| 97 | Screenshots/evidence | Owned native 17-route contact sheet, geometry, actual workflows, rich themes and controlled state fixtures. |
| 98 | Remaining limitations | Accepted model RAM, physical devices/monitors/providers, compositor attribution and retained constructor cost stated above. |
| 99 | Files added | `ui_next`, Spatial data/service, owned validators/demos/tests and these migration documents; exact final inventory pending. |
| 100 | Files changed | Production factory, existing event observability/rendering/settings/contracts/tests/package specification; preexisting phase work retained. |
| 101 | Obsolete old UI removed | Old visible root is retired; production uses the new root. Hidden compatibility widgets/controller code remain explicitly retained. Complete source extraction is not claimed. |
| 102 | Phase 11 readiness | Green for the full audit/public documentation phase, with the stated hardware/provider/constructor/compatibility constraints retained. |
