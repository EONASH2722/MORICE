# MORICE 0.9.1 follow-up audit

The audit started from clean commit `92b4ac094a4a88b310e99e5c7c8178505e57fec7`, after the previous 1,077-test software audit. The original Phase 11 baseline and its evidence remain unchanged.

## Reproduced and repaired

| Issue | Reproduction and resulting behavior | Regression coverage |
| --- | --- | --- |
| Granted iterable permissions prompt again | Pass an iterator containing a granted permission to a medium-risk capability. The second iteration previously appeared empty and requested an exact approval. Normalize once, retaining denied access and high-risk approval checks. | `test_permission_iterables_do_not_add_spurious_exact_confirmation` |
| Settings displays an unrelated page after zero matches | Enter an unmatched query. Every category hid but its previous page remained visible. Display an accessible empty state and explicitly restore the selected category when results return. | `test_settings_search_empty_results_do_not_show_an_unrelated_category` |
| Asynchronous Research creation loses edits or duplicates work | Click Create twice or edit the objective before delivery. Repeated submission was accepted and the callback read and cleared the current editor. Submit once, capture the objective, preserve a changed draft and recover from queue/worker failures. | Three Research creation cases in `test_renovation_workspaces_wake.py` |

Before the fixes, the new checks reproduced four failures and one passing worker-error case. After repair, all 106 focused permission and renovated-interface tests passed. The audit also confirmed that the environment's installed requirements are consistent (`pip check`) and that the established execution authorities remain singular.

## Additional user-reported defects

| Issue | Repair and evidence |
| --- | --- |
| Replies exist in history but paint blank with motion enabled | Reproduced in a native owned window. Assistant bubbles combined a child shadow with a parent opacity effect; remove these effects from chat rows. A pixel assertion and native before/after captures verify visible text. Background/Core animation remains enabled. |
| Typed prompts require a wake phrase | Treat Send as explicit activation and process the original typed request. Passive speech retains the wake gate. Normal and Live Action pipeline checks cover success and endpoint failure. |
| Title appears stale | Name and form-of-address fields save on editing completion; the composer uses neutral text. The real saved profile still held the older title, so the requested Sir preference is applied separately without resetting other settings. |
| Long-message wheel and reflow problems | Measure actual rich content, track width changes including cached browser layout, and forward vertical wheel input to the conversation. The 32,768-pixel native browser surface limit keeps a themed fallback scrollbar for exceptional documents. |
| Legacy Voice controls and duplicate editor | Adapt the existing Live Action widget to central design tokens and flowing controls, with one shared composer. Camera-off text no longer overlaps the response. |
| Clipped Context/Quick actions and message reactions | Reset the inherited fixed Quick actions width, measure wrapped composer height and use original vector reaction marks with appropriate button padding. |
| Deferred scroll after window destruction | Guard the late scroll callback against closed/deleted native controls. |
| Endpoint failures disappear from saved context | Retain the error turn as well as its visible response, so history and recovery show what happened. |

The first full follow-up run passed 1,082 tests and 62 subtests before these additional fixes. The targeted tests then reproduced eleven failures from the reported scenarios. After repair those eleven cases passed; the additional long-message resize/wheel case also passed.

The final full regression passed **1,094 tests and 62 subtests in 479.18 seconds**, at application source SHA-256 `f7dedf318b775650354645984f6f77b22d606cc3f0bbdb6ad13158a28cd55575` and test source SHA-256 `f5b4024dd732cd1d6632811bb6082dcd0f7b68a02478fb498f5cb480120dcad0`. This includes actual pixel assertions for visible assistant text, normal/Live Action success and endpoint failure, rich-text reflow and wheel forwarding, Context layout at compact/large-text sizes and the earlier runtime contracts. Artifact hashes and the matching package checks are supplied in the release's Package Contents and checksum files.

Native before/after evidence is retained locally under `build/phase11-091-reply-*`. Actual local Qwen inference returned a visible library description using the existing Parable Qwen3 4B weights and installed CUDA runtime, then shut down cleanly. Actual Vosk/Windows SAPI processing produced six complete non-aborted spoken replies and returned to listening, with zero pending workers or leases. Input/output audio used bounded memory transports; these are not physical microphone/speaker checks. An attempted text-only use of the separate SmolVLM vision weights failed its upstream chat-template parser and is not a certified general chat configuration; the failure was displayed, and those weights were not changed.

## Packages and current images

The exact 0.9.1 wheel contains all 217 source modules and passed native production-window checks with both the development dependencies and the separately installed clean dependency environment. The frozen executable contains 215 matching embedded modules; only the two CLI entry modules are omitted. Its 3,311 files include the small attributed offline Vosk model and exclude large generative/chat weights and private runtime data. Native startup runs outside the checkout with a system-only PATH and an isolated profile. The local installation preserves its three existing GGUF files and backs up the previous application.

All five older README images were replaced in place. The [23-image manifest](screenshots/current-manifest.json) binds the current native captures and website previews to their sources. The native capture traverses all 17 workspaces; graphs, physics and geographic fixtures are actual computations. Website production checks cover motion in all four themes, pause/resume, loaded screenshot hashes, keyboard tabs, desktop/mobile overflow and console errors. Live deployment and repository CI remain separately visible in GitHub Actions.

The [machine-readable follow-up validation](followup-validation-0.9.1.json) records software/package evidence without private profile paths. Release archives have CRC checks, metadata checks and SHA-256 manifests. Use the tagged 0.9.1 preview assets; the older 0.8.0 stable and Android releases retain their original scope.

## Retained controls

The redundant confirmation above was a defect and has been removed. Existing permission decisions, exact destructive-action approvals, device authentication, action verification, process ownership and resource protection remain. No unconditional permission bypass or unrestricted hazardous-research mode was introduced. The existing Phase 2 kernel, graph, workers, coordinator, shared state and leases retain their authority.

## Remaining limits

The concrete provider, physical hardware, available-RAM, rendering, SQLite and abrupt-process-exit limits remain documented in [release-audit-report.md](release-audit-report.md) and [verified-action-runtime-report.md](verified-action-runtime-report.md). They must not be relabeled as completed physical validation. No audit can guarantee the absence of every possible defect.
