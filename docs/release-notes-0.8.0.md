# MORICE 0.8.0

MORICE 0.8.0 turns voice, live camera context, automatic knowledge routing, fast desktop tools,
and verified Project execution into one local-first Windows application. The packaged build keeps
the main conversational model, Vosk speech model, llama runtime, and a compact SmolVLM2 vision
model on the computer. ElevenLabs speech and current web retrieval remain optional network paths.

## Live Action

- Live Action is a separate mode, not a reduced voice overlay. It retains typed chat, message
  history, attachments, graphs, scientific workspaces, Lab, Tools, PC actions, and Project builds.
- Offline Vosk speech-to-text captures user turns; ElevenLabs streams reply speech when a key and
  network are available. Barge-in interrupts playback and returns to listening.
- Leaving Live Action stops microphone capture, speech playback, camera capture, pending visual
  inference, and short-lived visual memory. Voice input/output do not continue in Normal Chat or
  Project Mode.
- Camera access is explicit. Frames remain in memory, vision runs on demand, and missing, stale,
  low-quality, or failed frames never produce a fabricated visual claim.
- The installed background listener recognizes MORICE, configured magic words, or double-clap,
  launches the app minimized without stealing foreground focus, never turns on the camera, and
  releases microphone ownership while Live Action is active. Cold-start events are single-flight,
  so repeated audio detections cannot create duplicate hidden app/model processes. Double-clap
  wake requires two sparse impulses with quiet separation, constrained-grammar guesses are
  confidence-gated, and Windows process leases use native liveness checks.

## Faster, More Grounded Execution

- Simple application, media, volume, and system requests use deterministic fast tools instead of
  paying for a conversational-model round trip.
- Runtime and model prewarm reduce first-turn stalls. Response milestones, bounded context, and
  streaming speech let useful output appear before a long local generation finishes.
- Typed goal state and capability inference select only registered host abilities. Device,
  network, Bluetooth, permission, and platform observations are normalized and reported honestly.
- Windows is the active privileged host adapter. The Android companion implements only explicitly
  paired and granted node tasks; Linux, macOS, and other physical devices remain extension
  contracts rather than fabricated control claims.

## Automatic Notes And Web Context

Users can ask naturally. MORICE selects relevant indexed notes automatically. Questions that
depend on current external information can use source-linked web context when the computer is
online; an unavailable network keeps the request on the local path and the response identifies
that freshness could not be verified. No special notes or web chat command is required.

## Project Mode Reliability

Full access now applies validated routine project files atomically and verifies the resulting
workspace. Folder-limited mode retains the red/green review step. Invalid model manifests are
repaired or sent through the narrow local fallback builder; a generated response is not counted
as success unless files exist under the selected work folder.

Project detection now covers Unreal, Unity, Roblox/Rojo, Godot, Android/Gradle, Visual Studio/.NET,
Node, Python, Java, Rust, Go, and static web projects. Full access records a durable target state,
exact artifact hashes/content checks, and available declared build/test results. The completed
processing card remains expandable as an observed execution trace.

## Android Companion And Device Network

- Added a lightweight Android 9+ companion with unified chat, opt-in STT/TTS, on-demand Camera2
  Live Vision, paired-device controls, and no desktop Project Mode.
- Added a common versioned MORICE node protocol using P-256 pairing, a compared six-digit code,
  AES-GCM task envelopes, replay rejection, time-limited pairing, directional capability grants,
  Windows DPAPI, and Android Keystore.
- Added desktop routing for explicit phone/tablet status, media, application, notification, and
  permission-gated camera requests. Local networking remains useful without internet.
- The signed Android APK has passed lint, compilation, minification, and APK signature validation.
  Physical-device camera/microphone/pairing QA remains required because this host has no attached
  phone and its Android emulator cannot use hardware acceleration.

## Context-Aware Speech

Verified deterministic PC actions use short acknowledgements without a large-model round trip.
MORICE differentiates started, found, running, verified, and failed states, so “Done” is reserved
for verified completion. ElevenLabs receives lightweight speed, stability, and style hints for
brief acknowledgements, normal explanations, and warnings without delaying synthesis.

## Media And Device Integration

- Amazon Music remains the configurable default music provider for this build. Application
  discovery, semantic search/select, Windows media sessions, transport controls, metadata, and
  system volume use structured paths before accessibility automation.
- Network state uses a bounded cached connectivity probe. Windows Bluetooth uses native read-only
  PnP discovery; a healthy device node is not mislabeled as actively connected.

## Install

Installer lane: keep `MORICE-Setup-v0.8.0-Windows-x64.exe` and every adjacent numbered `.bin`
slice together, then run the setup executable.

Portable lane: keep every `MORICE-Portable-v0.8.0-Windows-x64.zip.part*` file, its manifest, and
the reassembly script together. Run the script, extract the verified ZIP, and keep `MORICE.exe`
beside `_internal`.

Python lane: install `morice_ai-0.8.0-py3-none-any.whl`, run `morice`, and select a local model.
The Python package intentionally excludes model weights.

Verify downloaded files with `SHA256SUMS.txt` or `checksums.json`.

Android lane: install the signed `MORICE-Android-0.8.0-android.apk`, compare its SHA-256 value with
the adjacent manifest, then pair it from **Panel > Pair a device**. See `docs/android-companion.md`.

## Honest Boundaries

- General hosted conversational LLM providers are not integrated.
- ElevenLabs speech requires a valid key and network connectivity.
- Vision speed and accuracy depend on the local CPU/GPU, camera frame, model, and prompt.
- Bluetooth discovery is not equivalent to device pairing or active connection control.
- The Windows build does not claim operational control over Linux, macOS, Android, vehicles,
  robots, or unsupported physical devices beyond explicitly paired and granted MORICE node tasks.
- Android background camera capture, remote screen streaming, Bluetooth transport, shared-memory
  sync, file transfer, and internet relay remain future work.
- Windows binaries are unsigned unless a trusted publisher certificate is explicitly configured.
