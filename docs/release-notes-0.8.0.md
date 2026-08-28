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
  so repeated audio detections cannot create duplicate hidden app/model processes.

## Faster, More Grounded Execution

- Simple application, media, volume, and system requests use deterministic fast tools instead of
  paying for a conversational-model round trip.
- Runtime and model prewarm reduce first-turn stalls. Response milestones, bounded context, and
  streaming speech let useful output appear before a long local generation finishes.
- Typed goal state and capability inference select only registered host abilities. Device,
  network, Bluetooth, permission, and platform observations are normalized and reported honestly.
- Windows is the active privileged host adapter. Linux, macOS, Android, and authorized physical
  devices have extension contracts, not fabricated control claims.

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

## Honest Boundaries

- General hosted conversational LLM providers are not integrated.
- ElevenLabs speech requires a valid key and network connectivity.
- Vision speed and accuracy depend on the local CPU/GPU, camera frame, model, and prompt.
- Bluetooth discovery is not equivalent to device pairing or active connection control.
- The Windows build does not claim operational control over Linux, macOS, Android, vehicles,
  robots, or unsupported physical devices.
- Windows binaries are unsigned unless a trusted publisher certificate is explicitly configured.
