# MORICE 0.10.0 - local candidate validation

These local checks completed for the exact source and artifacts fingerprinted below. The release manifest records the final GitHub commit, remote checks and publication data; private installed-app verification is recorded separately. This local report does not claim that future commits or arbitrary installed models have been verified.

## Results

| Check | Actual result |
| --- | --- |
| Complete isolated Python regression | 1401 passed, 67 subtests passed in 1014.33 seconds |
| VNext | 14 tests passed; typecheck passed |
| Website | Production build passed; version/download-link source prepared locally |
| Version / source | Metadata consistency, compilation and whitespace checks passed |
| Public-content scan | No findings in the recorded tracked/unignored-file scan |
| Exact wheel | 253 source modules plus public assets matched; all 17 native workspaces opened; clean shutdown |
| Clean wheel install | Fresh virtual environment, no system site packages; declared dependencies installed; native NLUI/chart/table startup passed |
| Public frozen app | 251 embedded modules matched (CLI-only modules omitted); production factory, settings NLUI, actual three-row linked chart/table and style change passed |
| Private local candidate | Same canonical source parity; local answer-only hook independently verified; public EXE has no private hook |
| Resources | Native startup checks shut down cleanly with zero owned leases |
| Runtime | Regression and Windows candidates use CPython 3.12.15 and PySide6 6.11.2 |
| Real model sample | Existing Qwen3 4B matched 6/6 structured requests; no proposed actions executed; owned benchmark server stopped |
| New reasoning model | Supplied Qwen3.5 4B Q6_K produced visible answers in three 8,192-context samples and one 16,384-context / 6,144-output-cap sample; arithmetic/unit spot checks passed; model limitations below |
| Streamed math | Two actual KaTeX equations, zero parser errors, same bubble and preserved copy text in both frozen apps and clean wheel startup |
| Supplied rendering example | 14 KaTeX expressions, zero parser errors; DOM/layout check only; invalid window capture excluded |

Application source SHA-256: `87da2251ea0ed6f735d7d0f24f1c4ffd003df54517822c6c27a106189aaf26b7`.

Tests source SHA-256: `55906a6b618f5960d6c7b448d97f9736c728eee1bde16cb72b633801158e3245`.

Bundled web assets SHA-256: `8702a338fd126cac043e880172bc638bf825c34646c9230a6c3b7571cb79abfc`.

Public executable SHA-256: `f5d7d032ff7fef70fb88d40c20d4f44d497f4a179f884680ddc6d70099abd824`.

Wheel SHA-256: `d874da2301d0939631b81874b74402521f4c6ef52b0f9f6610dd04f290b8592e`.

Earlier checks exposed a packaging fixture below the automatic rich-response trigger, plus asynchronous rich-section reflow that could move a selected result outside the viewport. The fixture now exercises the actual trigger. Native response rendering preserves the reading position during source delivery and yields to subsequent navigation; a delayed actual-source regression checks both position and view lifetime. Direct native-test navigation marks the same input epoch as wheel/scrollbar input. Long regression runs on Python 3.14 encountered native access violations; a GUI-thread teardown fixture alone did not eliminate them. The final candidate therefore uses Python 3.12, matching repository CI, with the full result recorded above. Deferred Qt deletion and cyclic cleanup still run on the application thread between native tests, with automatic garbage collection enabled, following Qt's [QObject deletion and thread-affinity contract](https://doc.qt.io/qt-6/qobject.html#deleteLater). Failed or aborted runs were not counted as passes, and Python 3.14 stability is not certified by this result.

## Scope and reproducibility

An additional Python 3.12 run exposed a queued legacy-workspace item-model refresh after other UI work. Current lifecycle checks ignore retired owners and avoid rebuilding the renovated shell's hidden legacy lists; a native queued-after-close regression checks that path. The final local suite above includes that change. A test that created two watches within one Windows clock tick was also corrected to separate its fixture creations; equal timestamps still require clarification in production. Earlier failed runs were retained separately.

The [guide](nlui-rich-response-guide.md) defines 25 inventoried workflow groups, 37 typed natural-language descriptors, 18 rich kinds, actual performance measurements and conditions. Those counts do not certify every app, utterance, device or scientific assertion. Controlled screenshots/data/models are labelled; reference images supplied for inspiration were not copied as results.

Use `scripts/run_isolated_tests.py tests -q --tb=short`, `scripts/benchmark_nlui.py`, `scripts/benchmark_rich_response.py`, `scripts/verify_renovation_package.py`, `scripts/verify_renovation_frozen.py` and `scripts/smoke_phase10_frozen.py` to reproduce the corresponding checks. Model benchmarking needs an existing GGUF; it downloads no weights. Frozen startup runs under an isolated profile outside the checkout. Runtime/private data and QA logs are excluded from public packages.

The source/package version is 0.10.0; earlier releases are unchanged. The associated release manifest binds these local artifacts to the final commit and its remote checks. No end-of-life designation is made.

## Model observations

The supplied reasoning weights were registered using a same-volume hard link, adding zero extra weight bytes. The normal profile's default thinking selection resolves to that file and the separate fast selection remains Qwen3 4B. Explicit settings still take precedence. No model weights are included in public packages.

The three current-source CUDA trials reached their first visible output in approximately 2163 / 14704 / 166 ms. Their total times were 3041 / 20272 / 865 ms, with a 4613 ms cold load. The additional deep-profile sample took 36675 ms. These are small controlled requests on an RTX 3050 6 GB using a separately installed CUDA runtime, not general performance guarantees or broad engineering audits.

Earlier trials exposed an HTTP 400 from multiple initial system roles, reasoning-only empty output, a leaked concluding instruction when reasoning was disabled, and a wrong kilogram-to-milligram conversion. The adapter, finite token budget and Precision-mode SI references address those mechanisms. The final numeric spot checks are correct, but one constrained sample still labels a calculated value as measured. That label is not accepted as physical validation: model-generated prose is not a unit-checked receipt. Use actual Research calculations and their source provenance for numerical grounding. All owned benchmark servers stopped. CPU long-prompt performance and general model correctness are not certified. See the [reasoning and math notes](reasoning-math-0.10.0.md).

Physical microphone/wake/TTS timing, arbitrary third-party controls, real remote hardware, every DPI configuration and simultaneous sustained GPU inference/media load remain untested. STEP remains unavailable without a tested CAD backend. Compatible installed media providers are conditional. A verified software receipt does not establish engineering or physical performance.

## Files changed or added

The following is the current change inventory relative to the preceding source baseline. `A` means added, `M` means modified. It is not a claim that every file contains a separate user-visible feature.

| Status | Path |
| --- | --- |
| M | `CHANGELOG.md` |
| A | `MANIFEST.in` |
| M | `MORICE.spec` |
| M | `README.md` |
| M | `docs/README.md` |
| A | `docs/nlui-rich-response-audit.md` |
| A | `docs/nlui-rich-response-guide.md` |
| A | `docs/nlui-rich-validation-0.10.0.md` |
| A | `docs/reasoning-math-0.10.0.md` |
| A | `docs/release-notes-0.10.0.md` |
| A | `docs/rich-response-capabilities.md` |
| M | `installer/MORICE.iss` |
| M | `installer/version_info.txt` |
| M | `morice/agent_runtime/planner.py` |
| M | `morice/ambient/contracts.py` |
| M | `morice/ambient/service.py` |
| A | `morice/assets/web/morice-math.js` |
| A | `morice/computer_use.py` |
| M | `morice/connectors/github.py` |
| M | `morice/core.py` |
| M | `morice/kernel/adapters.py` |
| M | `morice/kernel/contracts.py` |
| M | `morice/kernel/permissions.py` |
| M | `morice/kernel/registry.py` |
| M | `morice/kernel/schema.py` |
| M | `morice/llm_client.py` |
| M | `morice/local_llama.py` |
| M | `morice/media_lab/capabilities.py` |
| M | `morice/media_lab/runtime.py` |
| A | `morice/nlui/__init__.py` |
| A | `morice/nlui/connected_domains.py` |
| A | `morice/nlui/contracts.py` |
| A | `morice/nlui/control_domains.py` |
| A | `morice/nlui/device_security_domains.py` |
| A | `morice/nlui/domains.py` |
| A | `morice/nlui/history_domains.py` |
| A | `morice/nlui/references.py` |
| A | `morice/nlui/response_domain.py` |
| A | `morice/nlui/runtime.py` |
| A | `morice/nlui/spatial_domain.py` |
| A | `morice/nlui/workspace_domains.py` |
| M | `morice/package_smoke.py` |
| M | `morice/pc_control.py` |
| M | `morice/personalization.py` |
| M | `morice/project_build/runtime.py` |
| M | `morice/project_workflows.py` |
| M | `morice/pyside_app.py` |
| M | `morice/research/history.py` |
| M | `morice/research/laboratory.py` |
| A | `morice/rich_response/__init__.py` |
| A | `morice/rich_response/calculators.py` |
| A | `morice/rich_response/contracts.py` |
| A | `morice/rich_response/exports.py` |
| A | `morice/rich_response/mesh.py` |
| A | `morice/rich_response/planner.py` |
| A | `morice/rich_response/registry.py` |
| A | `morice/rich_response/sources.py` |
| M | `morice/runtime_services.py` |
| M | `morice/settings.py` |
| M | `morice/spatial/contracts.py` |
| M | `morice/spatial/locations.py` |
| M | `morice/spatial/service.py` |
| M | `morice/ui_next/appearance_profile.py` |
| M | `morice/ui_next/appearance_view.py` |
| M | `morice/ui_next/bridge.py` |
| A | `morice/ui_next/control_settings.py` |
| M | `morice/ui_next/core_view.py` |
| A | `morice/ui_next/nlui.py` |
| A | `morice/ui_next/rich_charts.py` |
| A | `morice/ui_next/rich_controls.py` |
| A | `morice/ui_next/rich_export.py` |
| A | `morice/ui_next/rich_files.py` |
| A | `morice/ui_next/rich_mesh.py` |
| A | `morice/ui_next/rich_primitives.py` |
| A | `morice/ui_next/rich_response.py` |
| A | `morice/ui_next/rich_science.py` |
| M | `morice/ui_next/settings_view.py` |
| M | `morice/ui_next/shell.py` |
| M | `morice/unified_intelligence.py` |
| M | `morice/version.py` |
| M | `morice/workspace_state.py` |
| A | `scripts/benchmark_nlui.py` |
| A | `scripts/benchmark_rich_response.py` |
| M | `scripts/demo_verified_actions.py` |
| M | `scripts/promote_phase10_dist.ps1` |
| M | `scripts/verify_renovation_frozen.py` |
| M | `scripts/verify_renovation_package.py` |
| A | `tests/conftest.py` |
| A | `tests/fixtures/desktop_control_app.py` |
| M | `tests/test_ambient_connectors_security.py` |
| A | `tests/test_computer_use.py` |
| A | `tests/test_desktop_automation_permission.py` |
| M | `tests/test_fast_memory_ui.py` |
| M | `tests/test_llm_client.py` |
| A | `tests/test_nlui.py` |
| A | `tests/test_nlui_device_security.py` |
| A | `tests/test_nlui_media.py` |
| A | `tests/test_nlui_plugins.py` |
| A | `tests/test_nlui_references.py` |
| A | `tests/test_nlui_research.py` |
| A | `tests/test_nlui_response.py` |
| A | `tests/test_nlui_semantic.py` |
| A | `tests/test_reply_math.py` |
| M | `tests/test_research_lab.py` |
| M | `tests/test_reviewer_fixes.py` |
| A | `tests/test_rich_response_calculators.py` |
| A | `tests/test_rich_response_contracts.py` |
| A | `tests/test_rich_response_planner.py` |
| A | `tests/test_rich_response_sources.py` |
| A | `tests/test_rich_response_ui.py` |
| A | `tests/test_structured_control_backend.py` |
| M | `website/src/App.tsx` |
