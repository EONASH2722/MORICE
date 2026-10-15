# MORICE 0.9.2 desktop preview

This patch fixes an engineering question being replaced with an unrelated exam-score consolation. The host previously treated any percentage and any substring such as "result" or "exam" as an academic score, before contacting the selected model. A 70% converter-efficiency specification therefore produced a canned emotional response.

Brief personal check-ins now require direct personal wording and explicit academic context for score replies. Technical results, benchmarks, examples, quoted writing requests and failed compilations continue to the requested analysis. Actual short personal exam and emotional check-ins retain their quick responses.

Model identity questions require wording about the assistant itself. Embedded capability questions in a long audit no longer replace that audit with an inventory. References to an earlier AI answer no longer trigger a previous-message recall response. A bare mention of a mathematical model does not request a visual renderer, and an explicit instruction not to generate code prevents project-file creation routing. Existing deterministic commands and the Phase 2 runtime, permissions, resource leases and verification contracts remain in use.

Validation is recorded in [chat-routing-validation-0.9.2.md](chat-routing-validation-0.9.2.md). The reported full prompt is used privately for reproduction; public regression tests use a generic engineering example rather than publishing the user's design document. A routing check proves delivery to the selected model, not the scientific correctness of its answer.

The full regression run also exposed a media worker exit race: a child could flush its final JSON event between the parent's EOF read and its exit check. MORICE now drains the stable event file after confirming exit, preserving successful results and rejecting incomplete final events. A controlled real subprocess test forces this exact ordering; resource limits, ownership and cleanup remain active.

Extract the complete Windows x64 portable ZIP and start `MORICE/MORICE.exe` beside its `_internal` folder. Matching wheel, source distribution, tracked source, documentation, manifest and SHA-256 files accompany this release. Large language, vision and generative weights and private data are excluded. No new installer or Android APK is claimed.

The existing [0.9.1 follow-up audit](followup-audit-0.9.1.md) documents UI, voice and Live Action validation. Those results remain attributed to that version. Provider capabilities, available RAM/VRAM, physical audio/device validation and compositor frame pacing retain the concrete limits in the [release audit](release-audit-report.md). This patch does not establish an engineering model's numerical accuracy or eliminate every possible defect.
