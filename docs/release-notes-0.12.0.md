# MORICE 0.12.0 (UNLEASHED)

This amendment to the existing 0.12.0 publication adds Background Helper, a compact top-edge assistant for wake questions and selected screen content, black translucent Glass, and improved local speech recognition packaging. The version and publication stay the same. It retains the local Security Lab, holographic interface, chat thinking levels and previous reply/rendering fixes.

## Maintenance fixes

- Visual questions have room for a complete observation. If a reply is cut off or malformed, MORICE retries once with a compact response format and offers a next step if the retry fails.
- The helper keeps the message composer usable on smaller or scaled displays and clears dismissed content when a new interaction starts. A queued circle capture checks the current pause, permission, fullscreen, and application exclusion settings before capturing.
- Media jobs release their queue slots when history cannot be saved. Storage failures appear consistently in the task result and history, and generated files remain available for recovery from the media output directory.
- The website restores its animation when the browser restores the graphics context, including while animations are paused.

## Added

- **Background Helper:** opt in under Settings → Background Helper. Say “MORICE” or hold the middle mouse button and draw a closed loop to open the same compact assistant. The popup reuses the existing orb, models, speech and voice pipeline. It has a real Pause/Play icon, Enter to send, Esc to dismiss, and no close or expansion arrows.
- **Selected-content follow-ups:** one masked capture after the outline fades, kept in memory for follow-up questions. Capture and global gestures require separate consent; fullscreen pause and application exclusions are configurable. No idle screenshot loop or new cloud image-upload path is added.
- **Tray residence:** when enabled with a working tray, X hides the main window while the existing runtime remains available. Open, pause shortcuts or quit from the tray. No permanent orb is required for the helper.
- **Black Glass:** near-black main-window panels with native desktop translucency and adjustable Glass intensity, plus the curved popup's per-pixel transparent-black material. Opaque/high-contrast themes restore full opacity. Native frosted desktop blur is not implemented.
- **Orb desktop pet:** the home globe in a transparent, draggable desktop window; independently saved Orb/glow colors; subtle glow and smooth shuffled left/right/up/down idle turns.
- **Optional Orb voice wake:** explicitly allow the background microphone and say “MORICE” to speak through the small pet, keeping the main window hidden. Existing wake, speech, inference and playback owners are reused; Orb follows actual public activity and speech levels. Voice/Live Action keeps its surface while selecting registered workspaces and using their existing capabilities.
- **Focus continuity:** Windows overlays/dialogs pause the current visual pose and retain scene quality instead of resetting to angle zero.
- **Windows cursors:** the app and Orb use the system arrow, hand and text cursor with the user's Windows size and style. Custom cursor images, glow and trails were removed; the globe remains mouse-reactive.
- **Speech accuracy:** optional local Whisper Large v3 Turbo final recognition, with Small still supported, CPU INT8 computation, fast Vosk live text/wake detection, quiet-input normalization and bounded owned decoding. Faster Whisper decoder libraries and VAD data are included in Windows packages. Model weights remain separate downloads: approximately 1.6 GB for the standard Turbo checkpoint or 486 MB for Small. Accuracy and cold-start latency depend on microphone conditions and hardware.
- **Wake verification:** helper wake candidates must also match unrestricted recognition of the same short audio buffer, reducing false activations from a constrained wake grammar.
- **Transcript correction:** audio-based final refinement plus conservative assistant-name/workspace-command correction. Original and final transcripts remain available in speech diagnostics; unclear recognition requests a repeat and unavailable accuracy recognition reports its Vosk fallback.
- **Reply speech:** generated replies remain connected to TTS; Windows local speech can stream generated reply chunks without an ElevenLabs API key. Voice and Orb use actual playback levels.

- Signature/container inspection, SHA-256, entropy sampling, Unicode encoding/script detection and bounded structural parsing.
- Base64/Base32/hex/URL/HTML/GZIP decoding. Educational cipher transforms remain labelled candidates.
- Supplied-candidate ZIP AES/ZipCrypto recovery, optional password PDF recovery, and authenticated AES-GCM/ChaCha20-Poly1305 recovery for the documented manifest envelope.
- Measured candidate rejection cost, feasibility and remaining workload; actual attempts, cancellation, time/input/output/memory limits and explicit failure states.
- Transient secret entry, owner hints/conventions, named Windows DPAPI recovery keys and independent no-overwrite export verification.
- Official ADB discovery, Android USB/wireless pairing and exact-device diagnostics using an owned loopback server; Windows Bluetooth metadata.
- Static source findings with file/line/hash, dependency inventory and the existing Builder review flow.
- A localhost messaging challenge with actual send/store/recipient readback, planted-source repair through `filesystem.apply_patch`, and repeated authorization tests.
- One-origin header checks and an owner-supplied API mapping for real VOX test-account delivery.
- Natural-language Lab requests and rich results backed by actual local receipts/artifacts.

## Fixed and preserved

Explicit Voice selection now activates the session through navigation, home shortcuts, command search and natural language. Microphone/camera controls work from a passively restored Voice page without starting capture merely because the app reopened. Starting, unavailable and failed cameras keep their status visible and remain cancellable. Microphone failures no longer claim recording is active. Camera indicators describe this app's actual capture.

Obsolete speech handles cannot cancel newer recordings. Late warmup errors cannot overwrite a newer or stopped session, and queued transcripts cannot alter a new draft or submit after pause/resume or a settings change. Disabled recognition is reported explicitly.

This existing 0.12.0 publication includes the helper, Glass, reply, Orb, cursor and speech amendments; its version is unchanged. Missing decoder dependencies report a structured error instead of a frozen worker traceback dialog. A failed visualization announces the failure and continues with a normal written answer to the original prompt, without adding another user message or discarding an unsent draft. Interactive component failures show available source data as text, while formatted-page failures preserve the original answer and copy text. Missing sources and a second model failure are reported explicitly.

Practical either/or questions use a bounded model-assisted prerequisite check. The check tracks which objects each option actually brings to the destination, so an option that leaves a required object behind cannot win merely on travel convenience. Local-model samples covered bringing a car to be washed, correcting prior walking advice, and walking to collect a car already there. These samples are not a general intelligence benchmark.

Lab completion waits for Kernel verification and physical resource release before another job starts. Recovery preserves originals, rejects unsafe archive names and clears invalid partial output. The Lab scrolls at small sizes, advanced sources are collapsed and result history refreshes correctly.

Public and local private builds remain separate. The local private answer/content override is not included in public packages. Action authorization, integrity checks, resource limits and device pairing remain in both.

Reasoning and fast model profiles remain separately selectable, with existing chat thinking levels. Their weights remain separate. README navigation and badges are below the logo, and screenshots that predate this amendment are labelled.

## Scope and installation

Owned fixtures validate cryptography, API delivery and source repair. Supplied speech PCM and software geometry checks do not certify physical wake/microphone behavior, every middle-button application, elevated/fullscreen programs, sleep/resume or mixed-DPI hardware. No physical Android/Bluetooth device or actual external VOX deployment was certified. No live VOX message was sent for acceptance. Unsupported formats, missing secrets and unavailable providers remain explicit; strong random encryption is not promised recoverable. Legacy CRC and PDF readability are not AEAD authentication.

Windows setup needs all adjacent numbered `.bin` slices. Keep `_internal` beside the portable executable. Python 3.12+ packages and source/docs archives match the release. Verify assets using its SHA-256 manifests. These are unsigned Windows preview packages, not a hardware certification.

See the [Background Helper guide](background-helper.md), [Security Lab guide](security-lab-guide.md) and [Security Lab validation report](security-lab-validation-0.12.0.md).
