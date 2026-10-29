# MORICE 0.11.0 validation

This report covers the integrated holographic interface, three application themes, chat thinking controls, public activity receipts and voice presentation. The release includes a machine-readable validation receipt with exact source fingerprints, test totals and packaged checks. Local native evidence is retained under `output/globe-final-evidence/`.

## Reference and implementation

The supplied `WhatsApp Video 2026-10-29 at 4.04.42 PM.mp4` was decoded locally. Frames around 6.5–7.7 seconds informed the [reference specification](globe-reference-specification.md). The new renderer uses original procedural geometry, not a copied video or texture.

| Area | Implementation and evidence |
| --- | --- |
| Previous interface | A few software-painted paths and a detached surface were replaced by one application-wide native OpenGL surface. The old painter remains an explicitly labelled fallback. |
| Geometry and depth | Perspective-projected spherical grids, broken shell arcs, three independently rotating orbit families, central filaments, radial markers and moving point particles. Eight buffers total **1,105,680 bytes**. |
| Core, light and glow | A dense luminous core, thin emissive lines and fine point sprites sit inside a separate analytic violet halo. White uses opaque backing alpha and contrast-adjusted light; Dark/Glass use additive emission. No full-resolution bloom texture stack. |
| Appearance | White, Pitch Black and Glass use the same palette authority across all 17 routes, native menus/dialogs, scientific neutral backgrounds and rich responses. Historical profiles remain readable and map into the three current modes. |
| Independent colors | Globe Color and Globe Glow Color preview separately without rebuilding geometry or resetting orbital time. Existing atomic appearance storage persists both; cancellation restores the selected channel. |
| Boot state machine | DORMANT → IGNITING → PARTICLES_FORMING → WIREFRAME_FORMING → ORBITS_SYNCHRONIZING → GLOW_ACTIVATING → READY_IDLE, with separate WAITING_FOR_SERVICES and FAILED states. Skip finishes visuals without declaring services ready. |
| Actual boot sample | Native captured stages: ignition 0.221 s, particles 0.570 s, wireframe 1.115 s, orbits 1.848 s, halo 2.494 s and ready 2.946 s. These timings describe the owned test profile, not model loading. |
| Startup/readiness | Existing runtime construction and health checks control readiness. Model loading stays on demand. Navigation, minimize/restore, theme changes and wake activity do not restart the cold intro. |
| Pointer input | Local proximity/velocity illumination, hover distortion, surface-position click ripple, drag yaw/pitch with damped inertia, double-click reset, bounded interpolated wheel/touchpad zoom and context-menu colors. Chat owns its own wheel scrolling. |
| Continuous animation | Orbital angles advance continuously. Idle motion eases into pointer control and real work states, avoiding angle jumps when generation starts or finishes. Input remains active during generation. |
| Real state | Existing CorePresentation, Kernel/work events and VoiceRuntime provide state. No second model router, memory manager, task kernel or voice runtime was added. |
| Voice | The text composer and spoken-answer overlay are hidden in Voice. Actual playback/microphone level feeds a smoothed envelope. Controlled native samples of 0%, 85%, 15%, 0% produced the expected rise and decay; this is a port/visual test, not a physical microphone certification. |
| Thinking controls | Low/Medium/High/Extra high are in chat, with request-local snapshots. Local server payload tests verify 256/1,024/2,048/4,096 reasoning caps and reserved answer room. Medium and above select the thinking profile. |
| Public activity | Expandable bounded receipts report actual context, lookup, page access/extraction, model readiness, reasoning-token activity and answer writing. Unreadable pages retain an error. Raw model reasoning is not labelled verified evidence. |
| Chat and NLUI | Existing ordinary text replies, explicit rich-result selection, math finalization, saved context, history scrolling and first-party navigation remain in place. Supplied links are bounded external source data. |
| Existing capabilities | All 17 native routes opened under all three palettes. Projects, Research, Spatial, Media, Device Mesh, automation, security, plugins, history and their existing permission owners remain available. |
| Logo | Original MORICE logo assets are unchanged. The globe is assistant presence, not a replacement logo or geographic Earth. |

## Actual native evidence and measurements

The owned-window recording shows boot, orbital motion, hover, click, drag/inertia, touchpad zoom, reset, independent colors, chat, controlled thinking/streaming states and all three themes. Scripted states in that clip are labelled fixtures; they are not represented as real model or microphone work. Native screenshots cover the home/chat/settings/workspace surfaces and the separate voice presentation.

In a six-second native idle sample after recording stopped, the renderer averaged **21.33 paint frames/s**, with **62.66 ms p95 paint interval**, **0.41% whole-machine CPU**, and approximately **707 MB process RSS** after opening all workspaces. These are paint/timer and process measurements, not GPU timestamp queries or a guaranteed 60 FPS presentation rate. Interaction targets a higher cadence; idle and model/media pressure are deliberately throttled.

The whole-device counter sample reported an NVIDIA GeForce RTX 3050 6GB Laptop GPU, 275 MB used and 0% utilization at that instant. Other applications share that device; this does **not** attribute 275 MB to MORICE. Vertex-buffer allocation is measured directly; complete per-process graphics VRAM is not certified.

An actual Qwen3.5 4B Q6_K native chat request completed in **46.66 seconds**, while the globe rendered **725 frames** and accepted pointer input. The owned model process was stopped afterward and runtime shutdown reported no remaining leases. This validates delivery and coexistence for one request, not general answer quality or scientific correctness.

Native globe tests exercised actual device-pixel ratios **1.0, 1.25, 1.5 and 2.0**, with small, standard and wide render sizes, meaningful frame changes, click input and zero GL errors. Complete application layout was directly inspected at the host's 125% display scaling; this does not certify every physical monitor/DPI arrangement.

Reduced Motion, boot failure/waiting/skip, independent colors, inertia/zoom bounds, real 3D geometry, actual reasoning payloads, supplied-page limits/failures and reasoning-event metadata are covered by targeted tests. Minimize/restore preserves boot state and pauses hidden rendering. All owned native checks reported clean shutdown with zero remaining leases.

## Final checks and limits

The release's `MORICE-v0.11.0-Validation.json` and `release-manifest.json` record full application regression, executable/source parity, packaged native startup, Python package checks, installer/portable audits and their exact source fingerprints. Publication requires successful **CI** and **Release validation** for the same commit. Server asset sizes and SHA-256 digests are checked against the local packages. Interrupted or failing development runs are retained locally and do not satisfy the publication gate.

The final compact-window regression found that a selected rich-result header could remain outside a short chat viewport after pending layout work. Selection now settles the layout and brings the header into view, guarded by the conversation and user-scroll epoch. The original failing test and the delayed-source reading-position regression both passed after this repair.

OpenGL fallback, speech providers, protected third-party apps, JavaScript-only/authenticated pages, PDF/video reading and external media/CAD providers retain their documented limits. The supplied reference is a visual target, not a claimed numerical similarity score. Higher thinking effort increases a budget and cannot guarantee correctness. Physical wake recognition/TTS latency and every possible simultaneous external workload are not certified.

Changed code includes `globe_renderer`, `globe_geometry`, `globe_state`, `globe_input`, `globe_colors`, CoreView/CorePresentation, the shell/appearance/theme controls, voice presentation, reasoning settings/client, activity/page reading, neutral scientific canvas palettes, package smoke checks and the frozen build cache. New tests cover the corresponding contracts; existing behavior tests were updated only where the requested three-theme/voice design superseded the prior UI contract.
