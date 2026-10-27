# MORICE 0.10.0 — natural-language control and interactive results

MORICE now connects natural-language requests to its existing workspaces and verified tools, and presents actual results as interactive components in chat. This is a new desktop release. The original logo, themes, model selections and earlier duplicate-message/scrolling fixes are preserved. This release is not designated the final MORICE update.

**Reply-routing amendment (27 October 2026):** this existing release is updated with a correction for engineering prompts. Input tables remain context for a written answer; they no longer automatically become interactive response panels. Request a plot or visualization to explore supplied data. Device matching uses whole references and explicit commands, so “tabletop” does not mean “tablet”. Engineering challenge headings keep incidental physics/3D terms from opening an unrelated simulation. Automatic charts for real saved tool results remain supported. See the [amendment checks](reply-routing-amendment-0.10.0.md).

Download and fully extract the portable package, or keep Setup and every matching `.bin` file together before running Setup. Verify downloads against `SHA256SUMS.txt`. GGUF and generative media weights remain separate; existing installed models can be selected in Settings → Models.

An installed Qwen3.5 4B Q6_K GGUF is preferred for primary reasoning while explicit choices, older weights and the separate fast profile remain available. Strict system-message templates and reasoning-only empty replies are handled by the existing adapter. Streamed answers now finalize LaTeX, tables and code in the same bubble, preserving copy text and heading boundaries. See the [reasoning and math notes](reasoning-math-0.10.0.md) for actual compatibility checks and model limitations.

## Requests and permissions

Direct navigation, settings and supported UI changes use native APIs without model inference. More varied commands can use the existing local fast/thinking model router to propose schema-constrained intent data. Target selection and execution still belong to the Kernel and existing domain owners. The controller asks when saved names or timestamps are ambiguous; restored pending actions require explicit resumption and a fresh choice.

Examples include “Open my latest project”, “Run the project tests, then fix this project”, “Show project test results”, “Compare my latest two experiments”, “Show my latest CAD model”, “Pause the installed example plugin”, and “Find the chat about the UI”. Folder-limited project changes open the actual diff for review; existing Full access applies requested project changes through the established pipeline. Test, build and runtime receipts reflect commands actually run. A prepared proposal is not a finished build.

**Settings → Permissions & control → Desktop automation** is off by default. When off, requests for third-party app control explain how to enable it. Enabling it permits supported observed Windows accessibility operations and preserves consequential-action confirmations. Turning it off cancels active access and invalidates pending approvals. Protected/custom controls may be unavailable; MORICE does not fall back to blind input.

## Actual interactive results

The versioned response contract supports 18 native component kinds: metrics, status, validation, tables, charts, calculators, math, diagrams, timelines, progress, files, previews, meshes, assemblies, media, spatial results, simulations and comparisons. They read actual referenced records, calculations or files. Charts have linked tables, axes, series, style, selection and verified PNG/SVG/PDF export. Calculators perform real unit-aware recomputation. STL/assemblies display actual checked vertices and part identities, with camera, visibility, wireframe and exploded presentation controls.

Retained chats save bounded source references and display configuration in the existing history store. Reopening checks source freshness and files again. Heavy sections load near the viewport and release workers, players and mesh buffers when hidden or removed. Missing artifacts leave available files usable. Invalid or unavailable sections retain a readable error and the surrounding answer. CSV/JSON export preserves bounded actual source samples; PDF report export combines selectable summary text, actual data, source references, limitations and current chart figures through the existing export authority.

## Verification and limits

The real installed Qwen3 4B model matched all six sampled structured-intent trials; this small sample does not establish universal language understanding. A controlled 100-response/1,000-row native workload kept 100 mounted chat rows and one loaded chart section, with no model calls or leaked leases. Exact measurements, tests, architecture and the coverage denominator are in the [guide](nlui-rich-response-guide.md) and [integration audit](nlui-rich-response-audit.md).

See the [local validation report](nlui-rich-validation-0.10.0.md) for exact tests, package fingerprints and publication status. STEP import requires a tested CAD backend and remains unavailable. Media quality depends on a compatible installed provider/model. Device/security checks use authenticated owned fixtures, not certification of every physical device. Physical microphone/wake/TTS timing, arbitrary app automation, sustained inference/GPU pressure and every DPI configuration are not certified. Numerical model outputs and software integrity receipts do not establish physical engineering performance.
