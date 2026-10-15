# MORICE 0.9.1 desktop preview

This preview publishes the renovated desktop interface and the existing cross-phase runtime, with follow-up repairs from the release audit and reported UI problems.

- Research project creation submits once, uses the objective captured at submission, and preserves any new draft typed while it finishes. Admission or worker errors re-enable retry and keep the draft.
- Settings search displays an accessible empty state when nothing matches and restores the chosen category when results return.
- A granted permission supplied through an iterator no longer triggers a false exact-action confirmation. Required permissions, denied access and high-risk confirmations retain their existing behavior.
- Replies remain visible with motion enabled: chat rows no longer combine nested opacity and shadow effects that suppressed native painting. Endpoint errors also remain in conversation history.
- Pressing Send processes a typed request immediately. Passive speech retains its wake activation behavior. The composer uses neutral text, and name/title edits save when leaving the field.
- Long rich messages grow with their content, reflow to the actual available width and pass vertical wheel movement to the conversation. Only documents above 32,768 layout pixels retain a themed inner scroll area to bound the browser surface.
- Live Action uses the current theme, responsive camera controls and the shared composer. Context actions wrap without clipping, and message reactions use original vector icons.
- The existing kernel deadline fixture uses a controlled clock, avoiding a timing-dependent assertion on Python 3.12 Windows runners. The production deadline checks remain unchanged.

The desktop includes twelve distinct animated themes, Glass, continuous procedural motion, authored icons, a visible composer, one workspace navigation surface and the original logo. Updated repository screenshots show the current interface, including graph, simulation, project and personalization views.

## Downloads

Use the Windows x64 portable ZIP by extracting the complete `MORICE` folder and starting `MORICE.exe` inside it. Keep the executable beside its `_internal` folder. Install the wheel in Python 3.12 or newer with the required dependencies, or build from the source distribution. The documentation archive contains the current screenshots and reports. Published assets include SHA-256 checksums and a package manifest.

The portable archive includes the small offline speech recognition model and its attribution, but no large language, vision or generative image/video weights, user settings, credentials or private runtime data. Existing local models can be selected after extraction. The earlier Android companion release is separate; this release does not claim new physical Android validation.

## Validation and limits

The follow-up audit is recorded in [followup-audit-0.9.1.md](followup-audit-0.9.1.md). It distinguishes source tests, native package checks, actual local-model inference and actual Vosk/Windows SAPI processing with bounded memory audio transports. Physical microphone/speaker validation remains separate.

This remains a preview with partial and experimental hardware/provider support. Fresh heavy-model generation depends on sufficient available RAM/VRAM; the previously accepted host-RAM limitation remains. General desktop semantic understanding, external providers and physical audio/devices require separate validation. Decorative rendering does not promise 60 fps. SQLite and Windows process-ownership boundaries retain the concrete limits in the [release audit](release-audit-report.md).

Python 3.12 on Windows has coarse monotonic-clock ticks, so deadlines shorter than one tick do not have sub-millisecond precision. The packaged Python 3.14 executable uses the higher-resolution performance counter. Neither configuration promises real-time scheduling. The follow-up audit records the original CI failure, its fixture correction and the separate validation snapshots.

Permissions, exact approvals for high-risk operations, process cleanup, resource leases, verification contracts, device trust and computational research safety remain active. They protect existing work and keep reported outcomes tied to evidence. Passing the checks is not a guarantee that every possible defect has been eliminated.
