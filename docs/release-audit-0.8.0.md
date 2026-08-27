# MORICE 0.8.0 Release Audit

Date: 2026-08-27
Source branch: `main`
Release tag: `v0.8.0`

## Verified Baseline

| Gate | Result |
| --- | --- |
| Python regression | 448 tests passed |
| VNext runtime | 14 tests passed; TypeScript typecheck passed |
| Website | TypeScript and Vite production build passed |
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
| Background wake | Vosk opened the actual Realtek microphone at 16 kHz and entered magic-word/double-clap listening; Live Action lease pause/resume passed |
| Packaged Live Action | The frozen app entered the separate Live Action workspace, began real microphone listening, kept the camera off by default, opened the real camera only on request, reported memory-only capture, and stopped voice/camera I/O on exit |
| Packaged local control | “What is my current RAM usage?” selected `FAST_TOOL → system.status` and returned actual local memory values without a model call |
| Packaged wake entry point | `MORICE.exe --morice-wake-listener --self-test` exited successfully with code 0 |
| Network | Bounded live connectivity probe succeeded; offline behavior is independently covered by tests |
| Bluetooth | Windows native PnP discovery returned real device nodes; active connection state remained unknown rather than inferred from driver status |
| Amazon Music | Structured discovery/media routes and semantic search paths are covered; exact provider behavior still depends on installed app/account/session state |

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

## Capability Boundary

The audit does not claim general hosted LLM integration, verified control of unsupported operating
systems or physical devices, Bluetooth pairing/connection control, guaranteed Amazon Music
playback-position reporting, or vision accuracy beyond the processed frame. Unsigned Windows
binaries may display a publisher warning.
