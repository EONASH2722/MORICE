# MORICE 0.8.0 Release Audit

Date: 2026-08-28
Source branch: `main`
Release tags: `v0.8.0`, `v0.8.0-android`, and `v0.8.0-portable`

## Verified Baseline

| Gate | Result |
| --- | --- |
| Python regression | 474 tests passed; 59 subtests passed under pytest; the same 474 tests passed under unittest discovery |
| VNext runtime | 14 tests passed; TypeScript typecheck passed |
| Website | TypeScript and Vite production build passed |
| Android compile gates | Debug lint/build, instrumentation APK compilation, JVM test discovery, release lint/build, and `apksigner` verification passed |
| Version consistency | `0.8.0` validated from `morice/version.py` |
| Frozen Windows app | Clean rebuild launched from `E:\MORICE\dist\MORICE\MORICE.exe`; startup health reported 14/14 with zero critical failures |
| Release package audit | Portable, installer, documentation, source, wheel, and sdist lanes passed content and SHA-256 verification |
| Archive policy | Release pipeline rejects secrets, caches, private tooling, model files in source/package lanes, and unsafe archive paths |

## Real Host Checks

Tests below used this Windows host and its actual hardware/services. They are not simulated claims.

| Surface | Observed result |
| --- | --- |
| Camera | Integrated camera opened at 1280×720; 29 preview FPS; 71 frames; zero conversion failures; raw-frame storage reported false |
| Vision | SmolVLM2 500M Q8 model/projector prewarmed on CPU and processed a fresh camera frame in 8.84 s; JSON schema and quality gates were enforced |
| Microphone | The configured Windows input opened and completed a non-retained capture; Windows permission and device fallback paths were exercised |
| Speech | ElevenLabs prewarm succeeded; streaming playback started; barge-in stopped playback in 12.76 ms; a second utterance recovered successfully |
| Background wake | Vosk opened the actual Realtek microphone at 16 kHz; a two-minute packaged soak remained at one listener process, zero children, zero wake signals, and 201.6 MB working set; a separate 30-second memory-only classifier sample produced zero false clap or phrase activations |
| Packaged Live Action | The frozen app entered the separate Live Action workspace, began real microphone listening, kept the camera off by default, opened the real camera only on request, reported memory-only capture, and stopped voice/camera I/O on exit |
| Packaged local control | “What is my current RAM usage?” selected `FAST_TOOL → system.status` and returned actual local memory values without a model call |
| Packaged wake entry point | `MORICE.exe --morice-wake-listener --self-test` exited successfully with code 0; repeated wake events share one pending cold launch, clap pairs require impulse shape plus quiet gaps, and one-word wake results require scored final recognition |
| Network | Bounded live connectivity probe succeeded; offline behavior is independently covered by tests |
| Bluetooth | Windows native PnP discovery returned real device nodes; active connection state remained unknown rather than inferred from driver status |
| Amazon Music | Structured discovery/media routes and semantic search paths are covered; exact provider behavior still depends on installed app/account/session state |
| Android runtime | No compatible physical device was attached; the installed x86_64 emulator could not boot without the Android Emulator hypervisor driver, so camera, microphone, Keystore, installation, foreground service, and real phone↔desktop pairing remain physical-device QA requirements |

## Latency

With `Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf` on the installed RTX 3050
6 GB laptop GPU, a warm three-run benchmark measured 59.7 ms median first useful token and
59.53 visible tokens/second. The deterministic router measured 0.023 ms median over 5,000 runs
with zero model invocations. The first server/model warm-up took about nine seconds; MORICE starts
that prewarm in the background.

## Model Integrity

- Vision model SHA-256: `6f67b8036b2469fcd71728702720c6b51aebd759b78137a8120733b4d66438bc`
- Vision projector SHA-256: `921dc7e259f308e5b027111fa185efcbf33db13f6e35749ddf7f5cdb60ef520b`
- The packaged build must contain the main GGUF, the vision GGUF/projector pair, the bundled
  llama runtime, the Vosk speech model, and the embedded wake-listener entry point.

## Release Artifact Gate

The release pipeline built the Windows executable, disk-spanning installer, split portable archive,
documentation archive, source archive, wheel, and source distribution. Package-content audit and
SHA-256 verification passed, as did startup and UI inspection of the untouched clean rebuild.

The Android lane built a minified, resource-shrunk Android 9+ APK signed by the dedicated MORICE
Android key. `apksigner` reported a valid signature with a 4096-bit RSA signer. The Android release
contains the APK and its exact SHA-256 manifest; it does not claim Play Store publication.

## Capability Boundary

The audit does not claim general hosted LLM integration, verified control of unsupported operating
systems or physical devices, Bluetooth pairing/connection control, guaranteed Amazon Music
playback-position reporting, Android runtime behavior that could not be exercised without hardware,
or vision accuracy beyond the processed frame. Unsigned Windows binaries may display a publisher
warning.
