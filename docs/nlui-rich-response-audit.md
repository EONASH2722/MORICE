# Natural-language and rich-response integration audit

Baseline: MORICE 0.9.5, commit `604eda11778464bd35a6b72e3f8441fde6c90271`. The two supplied briefs are implementation requirements. The reference screenshots describe interactions; their numerical values, validation passes, generated files and CAD geometry are not application evidence.

## Existing owners and integration points

| Concern | Existing owner | Finding and integration decision |
| --- | --- | --- |
| Composition | `runtime_services.RuntimeServices` | Reuse its Kernel, workers, resources, agent coordinator and lazy domain services. |
| Capabilities | `kernel.CapabilityRegistry`, `CapabilityDescriptor` | Real typed descriptors, schemas, permissions, health, resources and verifiers already exist. Add linked natural-language metadata, not a competing execution registry. |
| Planning/execution | `kernel.TaskGraph`, scheduler, `AgentCoordinator`, `autonomous_builder` | Reuse dependencies, cancellation and existing Builder authority. Never execute a command taken directly from model prose. |
| Verified actions | `action_runtime.VerifiedActionRuntime` | Existing independent application, browser, filesystem and owned-process observation. Retain exact approvals and action journal. |
| Desktop policy | `pc_control.PermissionBroker`, `unified_intelligence.PermissionController` | Existing exact one-use confirmations and category policies. Add an explicit, initially disabled desktop-automation gate to these authorities. |
| Third-party UI | `pc_control.UnavailableComputerUseAdapter` | Currently explicitly unavailable. Application/window helpers exist, but general accessible-control operation is missing. The already declared `uiautomation==2.0.29` dependency was absent from the development environment; install the declared dependency and implement observed, bounded UIA operations with truthful unsupported states. |
| Conversational PC routing | `pc_control.FastActionRouter`, `intent_router`, presenter callbacks | Many routine actions exist, but compound operations escalate to prose. Extend with first-party typed bindings, bounded references and pending clarification. |
| Models | `ModelRouter`, `llm_client`, shared lifecycle | Keep fast/thinking selection and serialized model residency. Direct UI operations require no model. |
| Production UI | `ui_next.shell.RenovatedWindow`, `UiBridge` | Internal navigation/settings APIs exist. Use them directly, never third-party-style mouse automation for MORICE itself. Heavy domain work remains in existing workers. |
| Settings/theme | `settings`, `SettingsWorkspace`, `ThemeEngine` | Add searchable Desktop automation/Natural language controls; use validated theme tokens and persisted settings. No logo or branding change. |
| Voice | `wake`, existing STT/TTS and presenter `on_send` | Text and supported voice transcripts must reach the same controller. Physical microphone/audio certification remains a separately measured condition. |
| Chat/memory | `research.history.ChatHistory`, current-chat retrieval, `MemoryManager` | Stable indexed IDs and bounded windows already exist. The attachments field can hold bounded rich-response metadata. Do not create another database or inject full transcripts. |
| Current chat output | `ChatBubble`, `RichContentView`, inline visualization workspaces | Markdown, code and offline KaTeX already render. Reuse them; rich sections need typed validation, data provenance and a lazy renderer host. |
| Charts/diagrams/math | `ChartCanvas`, `DiagramCanvas`, graph plugins | Native deterministic renderers exist. Reuse their primitives/backends where suitable; add data-linked table/hover/series controls without importing a new large plotting stack. |
| CAD | `research.engineering` | Bounded generated STL and actual mesh validation exist; the current scene illustrator is not an imported CAD viewer. Add bounded binary/ASCII STL parsing and actual-part preview. STEP has no installed OpenCascade backend and must be reported unavailable until a real adapter passes testing. |
| Research | `ResearchRuntime`, `VirtualLaboratory`, scientific registry | Real parameters, verified calculations, persisted experiments/runs, comparisons and exports. UI controls must dispatch these existing capabilities and retain their limits. |
| Media | `MediaLab`, history/artifact/export/preview services | Existing actual provider discovery, references, queued generation and cancellation. Reuse IDs; missing models are unavailable, never placeholder success. |
| Spatial | `SpatialService`, `SpatialView` | Existing text commands, selected markers, deterministic distances and globe. Extend referential commands without another geospatial engine. |
| Other domains | Device Mesh, Ambient, connectors, security, history/workspace adapters | Existing domain authority and authorization remain intact. Expose meaningful supported operations with explicit availability and verifiers. |

## Delivery order and acceptance

1. Complete capability/UI exposure inventory and record supported, unavailable and untested entries with an explicit denominator.
2. Implement and test desktop permission persistence, immediate revocation, disabled guidance, bounded observed UIA input and existing consequential confirmations.
3. Add the shared natural-language adapter, stable active-context references, clarification/expiry, typed navigation/settings/domain bindings, existing TaskGraph workflows and cancellation. Validate through production Qt text/voice entry points.
4. Add the versioned rich-response contract, strict payload/action/reference validation, component registry and lightweight presentation planner. Plain replies retain the fast path.
5. Integrate real metrics/status, virtual tables, linked charts, deterministic calculators, diagrams/timelines, verified artifact actions/previews, actual STL/assemblies and domain results. Persist bounded schemas through existing history and rehydrate lazily.
6. Validate component actions through NLUI, native UI interaction/screenshots, unsupported-provider behavior, permissions, source freshness, malformed input, long chats, reduced motion and resource cleanup. Measure latency using controlled fixtures rather than copying reference numbers.
7. Run full regression, clean frozen and Python-package checks, update documentation/README, publish a **new release** as explicitly authorized, and update the local dist application. Preserve the prior local-only answer-policy preference separately from the canonical public build.

The README introduction, navigation links and badges have been moved directly below the title as requested. No completion or universal third-party support claim is made by this baseline audit. Detailed measured results and the final feature matrix will replace pending entries as implementation and verification progress.

## Structured proposal transport

Control proposals use schema-constrained decoding through the existing shared streaming backend and remain independently validated by `WorkflowPlanner.capability_steps` before Kernel execution. The host builds the schema from the selected capability catalog; model text cannot supply a schema or permission grant. Ordinary chat does not request a structured format. Local llama-server uses the documented [`json_object` schema format](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#post-v1chatcompletions-openai-compatible-chat-completions-api); the existing local Ollama transport uses its documented [`format` schema](https://docs.ollama.com/capabilities/structured-outputs). A supported transport and valid JSON do not establish correct intent: the real local-model trial also checks the selected capability and arguments.

## Implemented integration

The implementation now has 37 typed natural-language descriptors in the existing Kernel and 18 rich component factories. The [guide](nlui-rich-response-guide.md) records all 25 inventoried workflow groups, conditions, examples, verification and the exact coverage denominator. It distinguishes native/owned-fixture tests from real provider, microphone and remote-hardware certification.

Observed Windows UIA controls, project proposals/test/fix/build review, exact device-file transfer, security finding containment, installed-plugin lifecycle, indexed transcript search, current-chat rich controls and report/data/chart exports are implemented. Each uses the prior owner and existing authorization path. Private answer-policy overrides remain outside canonical/public packages and cannot alter action policy.

The native checks exposed and fixed a Windows checkpoint replacement race with rich-progress reads, a frozen execution-context mutation in chained project selection, a UI port import shadowing `Path`, and legacy custom permission checks bypassing explicit host denials. Native validation also covers chart/table interaction preserving scroll position, source refresh and lifecycle disposal. QA fixtures now isolate APPDATA/LOCALAPPDATA as well as model/runtime/settings roots.

PDF reports use the existing native Qt PDF backend and the same registered export authority. They contain selectable escaped text, actual bounded rows/source revisions, current chart figures where available and explicit limitations. CSV neutralizes formula strings; JSON includes sample/provenance/units. File replacement remains no-overwrite with independent hash readback. A capture must be an in-process owner receipt; model JSON cannot forge one.
