# Natural-language control and interactive results — 0.10.0

Use the normal chat composer or a delivered voice transcript. MORICE resolves supported direct commands without loading a model. Other supported first-party requests can use the selected local fast/thinking backend to propose typed intent data. The existing Kernel validates, authorizes, schedules and verifies actions. A model cannot supply permission grants, executable UI code or command-line authority.

## Starting points

- “Open Settings”, “Open memory settings”, “Make the UI purple”, “Reduce the glow”, “Maximize MORICE”.
- “Open my latest project”, “Run the project tests, then fix this project”, “Show project test results”. Select the intended project folder first. Tests require confirmation of the discovered command; folder-limited changes open the real diff for review. A proposal is not a completed build.
- “Show my research projects”, “Show my latest experiment results”, “Compare my latest two experiments”, “Show my latest CAD model”. Sources must actually exist; tied or missing timestamps prompt a choice.
- “Show the data table”, “Use a bar chart”, “Set force to 7 N”, “Explode this assembly”, “Export this graph as PDF”. Select/open the intended result in the current conversation first.
- “Export this table as CSV”, “Export this data as JSON”, “Export this as PDF”. Data exports contain the bounded source sample, explicitly labelled as such; complete experiment exports remain available from the experiment's actual file collection. PDF reports retain selectable text, current source references, limits, actual tabular values and available current chart figures.
- “Find the chat about the UI”, “Show my saved preferences”, “Pause the installed example plugin”. Retained chat search uses the existing transcript index and excludes session-private/current-chat records. Older unindexed archives need History → Rebuild index.

## Desktop permission and model settings

**Settings → Permissions & control → Desktop automation** starts off. Requests for third-party app control then explain where to enable it and ask you to resend. Turning it on allows requested, supported accessibility operations while preserving existing confirmations. Turning it off revokes pending approvals and cancels active control. MORICE's own workspace navigation does not need PC control. Protected/password/custom controls without a supported observed interface remain unavailable.

Settings also exposes Natural language control, automatic workspace opening, plan visibility and Auto/Compact/Detailed/Visual/Technical response presentation. Permission grants, credentials, device pairing and plugin permission review remain explicit native controls. Natural-language requests cannot grant themselves access.

**Settings → Models** retains separate generative/thinking and Fast Reply selections and automatic routing. Select an existing GGUF or supported installed local backend. The release contains no generative model weights. Qwen3 4B matched the six tested structured requests; arbitrary engineering reasoning and intent recognition still depend on the selected model and supplied data.

## Architecture, context and recovery

`RuntimeServices.nlui` registers descriptors in the existing Kernel registry. First-party UI operations reach `WindowCapabilityPort` through the existing queued bridge. Domain adapters call the existing Research, Builder, Spatial, MediaLab, Mesh, Ambient, connector, security, plugin, history and memory owners. There is no second task executor, permission authority, model runtime or history database.

Active context includes the actual window/chat/project, selected objects and current question. Exact IDs and actual timestamps resolve references. Ambiguous references ask for a bounded choice; clarification expires after 15 minutes. Reopening a retained chat can restore a pending question, but requires resumption and a fresh choice. Previous approvals are never replayed. Explicit compound operations use the existing TaskGraph dependencies. A failed project test may admit a requested repair only when its authorized completed command produced an actual failure receipt; denial/cancellation/timeout do not admit repair. Passing tests do not trigger a failing-test repair.

Current-chat retrieval and approved personal preferences retain their earlier bounded scope. Preferences cannot establish permissions or execution authority. Explicit cross-chat search returns indexed matching snippets and stable message references; it does not inject full unrelated transcripts into the model.

Cancellation uses existing tokens and owners. Partial results preserve completed steps and disclose failure. Appearance undo checks that the appearance has not changed again; project undo remains the existing verified patch operation. Async source callbacks are scoped to the owning chat/section generation so removed results cannot update a new view.

## Workflow exposure matrix

The denominator here is **25 explicitly inventoried workflow groups**, listed below. All 25 have a natural-language entry point: **25/25 binding coverage for this inventory**. This does not mean every UI button, arbitrary utterance, third-party app, provider or physical device was automatically exercised. “Conditional” describes an implemented binding whose real execution also needs an installed provider, review, scope or device. Individual test assertions and the small model sample are separate evidence, not this coverage denominator.

| Group | Binding/owner | Verification and conditions |
| --- | --- | --- |
| 1. Workspace navigation | `ui.navigate` | Actual native route; no model. |
| 2. Settings and exposed preferences | `ui.settings`, `ui.preference` | Native control and saved state; sensitive grants remain manual. |
| 3. Appearance and undo | `ui.appearance`, `ui.undo_appearance` | Typed colors/scales, actual theme state; same-chat undo freshness. |
| 4. MORICE window | `ui.window` | Actual geometry/state/focus/screen; available-monitor bounds. |
| 5. Research notebooks | `nlui.research.*` / ResearchStore | Actual saved IDs, choice/recency and selected workspace. |
| 6. Experiment lifecycle | Research laboratory | Actual persisted runs, run/pause/cancel and owner state. |
| 7. Saved calculations/CAD/files | `nlui.research.record` | Actual record revision, file hashes and STL bytes. |
| 8. Experiment comparison | Research laboratory | Aligned actual parameters, units and sampled outputs. |
| 9. Saved project folders | `nlui.project.open` | Actual existing saved directory and native selection. |
| 10. Project inspection/tests | `nlui.project.check` | Existing tools and discovered command receipts; exact confirmation. |
| 11. Project proposal/repair/build | `nlui.project.propose` / Builder | Actual diff/baselines, native review, existing apply/build/repair pipeline. Model/toolchain conditional. |
| 12. Saved build/test results | `nlui.project.result` | Known checkpoints for selected project; actual test receipts. |
| 13. Spatial calculations | `nlui.spatial.command` | Existing place identities, WGS84 calculations, current-chat source snapshot. Online lookup conditional. |
| 14. Prompt media generation | `nlui.media.generate` | Existing queue and actual provider health; compatible local provider required. |
| 15. Edits/variations/animation | `nlui.media.transform` | Actual selected image/hash and original request; provider/workflow conditional. |
| 16. Media results/comparison/save | MediaLab bindings | Actual available outputs, selected destination and hash. |
| 17. Device file transfer | `nlui.mesh.send` | Exact source artifact/device confirmation, trusted permission and remote inbox hash. Authenticated loopback fixture tested. |
| 18. Watches | `nlui.automation.control` | Existing saved watch state, actual timestamps, confirmation and deletion readback. |
| 19. GitHub issue workflows | Existing connector | Real repository/scope and exact create confirmation; owned loopback transport tested, no external issue posted by QA. |
| 20. Security observation/containment | `nlui.security.control` | Exact actual finding/process identity/file hash, existing authorization and receipt; harmless owned fixture only. |
| 21. Retained chat search/open | `nlui.history.control` | Existing FTS/stable IDs, original matching message, retention/edit invalidation. |
| 22. Preferences | Existing memory commands plus `nlui.memory.list` | Explicit save/forget, scoped approved records, settings and DPAPI protections retained. |
| 23. Installed plugin lifecycle | `nlui.plugin.control` | Existing manager, permission review and exact confirmation; actual owned subprocess state. |
| 24. Displayed rich-result actions | `nlui.response.control` | Actual current-chat component/source, typed display edits, verified chart/data/report export. |
| 25. Third-party accessible controls | Existing PC/verified-action runtime | Desktop opt-in plus existing category/action rules; actual owned Windows UIA fixture. Arbitrary app coverage is not claimed. |

## Rich-response contract and renderer coverage

There are **18 registered component kinds**. Registry presence is not by itself a functional test: native tests exercise real data, controls, decoding, source refresh and disposal. Tables/charts read bounded samples and the complete experiment CSV remains a separate actual artifact. Units and provenance appear with results. Statistical or physical uncertainty is not manufactured when no source supplied it.

| Components | Behavior |
| --- | --- |
| Metrics, status, validation, comparison | Actual fields/units, arithmetic deltas, command evidence and refreshable recorded checks. |
| Table, chart | Paged/filterable/sortable tables; line/bar/scatter, series, hover, axes, point/row linking and saved selection. |
| Calculator, simulation | Registered bounded scientific models, unit conversion, actual recomputation, explicit costly-run controls. |
| Math, diagram, timeline | Existing mathematical rendering, typed explanatory or actual-source diagrams, real recorded event ordering. |
| Progress | Actual owner state; measured run fractions only. Stage-only jobs get no guessed percentage. |
| Files, preview, media | Actual file list, selected-destination no-overwrite export, PNG/SVG/PDF/code/CSV/video decoding and disposed players. |
| Mesh, assembly | Actual bounded binary/ASCII STL vertices, camera/fit, part selection/visibility, wireframe, exploded offsets and parts grid. |
| Spatial | Existing native geographic canvas and independently computed distances/units. |

Plans use schema version 1, at most 24 components and 64 KiB of metadata. Paths, scripts, arbitrary callbacks and permission tokens are forbidden configuration. Only trusted factories can render registered kinds. Source revisions/hashes are checked again for export. CSV string cells that could become spreadsheet formulas are neutralized; numeric values remain numeric. PDF composition escapes all text and uses actual current data; it does not load arbitrary web content. Unsupported plans keep ordinary chat text readable.

Plans and spatial/query source snapshots use existing assistant-message attachments. Heavy data and model weights are not embedded. Scrolling or hiding releases offscreen renderers and cancels their jobs. Current display configuration survives rebuild/reopening, including chart axes/series/filter/style/selection, calculator parameters and mesh camera/parts/explosion.

## Measured validation

The subsequent [reasoning and math addition](reasoning-math-0.10.0.md) prefers an installed Qwen3.5 4B Q6_K primary, preserves the separate fast profile, normalizes strict chat templates and fixes mathematical streamed replies. Its model samples are separate from the structured-intent benchmark below.

The final local structured-model trial used the existing Qwen3-4B-Instruct-2507 Q4_K_M GGUF, shared streaming adapter and host-selected schema. **6/6 requests matched** expected capability/arguments; proposals were not executed. Cold model load was 8,266 ms. Six proposal wall times were approximately 7,652 / 1,952 / 1,537 / 2,255 / 2,284 / 2,703 ms. Direct navigation resolution over 100 iterations used zero model calls, with 0.047 ms median and 5.73 ms maximum. The isolated benchmark server stopped afterward. This is a small intent sample, not an intelligence score.

The reproducible native benchmark (`scripts/benchmark_rich_response.py`) used 100 rich responses backed by 1,000 actual supplied rows. Constructor-to-window time was 2,753 ms; ordinary append median 23.7 ms; rich append plus intentional 30 ms event settling median 45.9 ms / p95 63.2 ms. Mounted chat rows stayed at the 100-row limit; one chart section was loaded at the end, with zero pending deliveries. RSS grew 32.6 MiB during this controlled workload. UI timer intervals were 20.7 ms median / 42.1 ms p95, not a compositor FPS measurement. Shutdown left zero owned leases/workers. No model inference ran during this renderer workload, and no sustained GPU-pressure claim is made.

Native acceptance includes linked chart/table/history restore, real unit edits/recomputation, actual two-part STL and exports, decoded PNG/SVG/PDF and video playback cleanup, math/diagram/geography, text and delivered-voice navigation, actual project tests and review/apply/build/repair, job controls, transcript-query results, LOW quality/reduced motion/high contrast/theme changes, and virtualized-row worker cancellation. Additional backend tests cover ambiguity, restart continuation, denial, malformed payloads, stale/missing files, units, scoped media, authenticated transfer, plugin processes and harmless security containment. Packaging uses the production window factory under an isolated profile and includes a native NLUI/chart/table probe.

Full regression and local package fingerprints are recorded in the [validation report](nlui-rich-validation-0.10.0.md). The eventual release manifest must match its final commit. Publication remains a separate step after those checks and CI pass.

## Availability and limits

STEP import/tessellation is unavailable without a tested CAD backend; STL is never presented as STEP. Media requires compatible installed weights/providers. Physical microphone/wake/TTS latency, arbitrary third-party controls, real remote hardware, all DPI configurations and simultaneous sustained GPU inference/media load are untested. Declining or denying a requested action does not authorize a fallback method. Unsupplied evidence, experimental measurements, validation passes, generated downloads and screenshot numbers are never manufactured.

“Make a report from this” composes available actual sources. It cannot create missing CAD, engineering evidence or a complete hardware validation package. Tables in reports are bounded; the report says how many rows it contains. A local model can still misunderstand a request, and unverified natural-language assertions remain unverified even inside an exported report.

See the [architecture audit](nlui-rich-response-audit.md), [component inventory](rich-response-capabilities.md), [release notes](release-notes-0.10.0.md) and the earlier [model/memory guide](fast-memory-guide.md).
