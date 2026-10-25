# Rich response capability inventory

This records the initial inventory and resulting implementation. Reference screenshot values and files are not evidence. The existing Kernel, domain services, history database, design tokens, model router and renderer lifecycle remain the owners. Measured native behavior and the explicit coverage denominator are in the [guide](nlui-rich-response-guide.md).

| Response | Existing renderer/source | Integration work | Verification and limits |
| --- | --- | --- | --- |
| Plain text, Markdown, code, math | ChatBubble, RichContentView, offline KaTeX | Keep the current fast path; typed math sections reuse this renderer | Existing escaped/sanitized rendering; no executable model HTML |
| Metrics and comparisons | Research runs, Builder cards, runtime snapshots | Native responsive cards tied to actual source fields | Show units/provenance; unavailable fields have no fabricated value |
| Validation/test results | Kernel verification, Builder command evidence | Expandable native receipts and check summaries | A software receipt does not certify scientific assumptions or hardware |
| Data tables | Existing Research result pages | QAbstractTableModel paging/filter/sort; linked selection | Bound fetched rows; complete exports stay with the domain owner |
| Charts | Existing ChartCanvas/GraphCanvas and domain calculations | Native line/bar/scatter views with hover, series control and linked table | Actual source rows, explicit axes/units, bounded plotting/downsampling |
| Calculators/strategy selection | ScientificTools, simulation registry, harvester equations | Typed parameter controls using existing guarded backend calculations | No eval/exec; finite values, units and model limits; label computational outputs |
| Workflow/relationships/timeline | DiagramCanvas, Research graph, task events | Typed accessible diagrams and actual event timelines | No model-invented execution progress or completion percentage |
| Live jobs and simulations | Kernel events, Research laboratory, Media queue | Scoped refresh/control and independent state rereads | Existing cancellation/approvals; no replay after restore |
| Files/download collections | Research exports, Media artifacts, Builder artifacts | Verified file collection and selected-destination export | Existing file policy, source hashes, actual copy/readback, missing/stale disabled |
| Images/video/PDF/code/CSV | ui_workspace preview widgets and Media ArtifactViewer | Lazy reuse of actual preview components | Supported local files only, bounded decode and no substitute content |
| STL | Research engineering emits real binary STL; SceneCanvas is illustrative | Bounded actual STL parser and native projected mesh viewer | Check actual bytes/hash, finite vertices and triangle bounds; no invented geometry |
| Assembly/parts grid | Actual imported/generated part meshes | Camera controls, selection, visibility and exploded transforms | Each part must have an actual verified mesh; transforms are presentation state |
| STEP | No tested OpenCascade backend installed | Expose an honest unavailable state | Do not relabel illustrations or STL as imported STEP |
| Spatial | Existing native globe/map and SpatialService | Reuse actual geographic state/units/path results | Real location identities and existing deterministic verifiers |
| Media | Existing MediaLab providers/history/verified artifacts | Actual preview/comparison and current workflow availability | Missing provider/model stays unavailable; generated content is labelled |
| Persistence | Existing ChatHistory attachments/UI state | Store versioned source references and bounded display configuration | Requery sources on restore; no approval tokens, binary meshes or replayed actions |
| Theme/accessibility/resources | Renovation ThemeEngine, renderer clock, reduced motion | Native palette, focus, accessible labels, lazy construction/disposal | Hidden/offscreen results must not run background animation or inference |

All 18 component kinds are registered. Native tests exercise actual source-backed controls and lifecycle behavior; STEP remains unavailable. Chart PNG/SVG/PDF, bounded CSV/JSON samples and selectable PDF response reports now use the existing Kernel export policy and independently verified destinations. The bounded GitHub issue listing uses the existing connector transport and scopes, following [GitHub’s repository issue API](https://docs.github.com/en/rest/issues/issues#list-repository-issues); filtering is explicitly limited to the fetched page.
