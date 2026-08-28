# MORICE Android Companion

MORICE Android is a lightweight companion node for MORICE Desktop. It includes unified chat,
opt-in voice, on-demand Live Vision, device status, media controls, application launch, and a
secure connection manager. It intentionally does not include desktop Project Mode, repository
tools, or local large-model runtimes.

## Install

1. Download `MORICE-Android-0.8.0-android.apk` from the **MORICE Android Release**.
2. Verify its SHA-256 value against the adjacent manifest.
3. Allow installation from the browser or file manager you used to download it.
4. Open MORICE Android and select **Devices**.
5. On the desktop, open **Panel > Pair a device**. Pairing remains open for two minutes.
6. Enter the desktop LAN address and port shown by MORICE, then confirm that both devices show
   the same six-digit code.

Both devices must be on a mutually reachable local network. Internet access is not required for
pairing or encrypted node tasks.

## Security Model

- P-256 ephemeral key agreement derives a unique 256-bit session key.
- AES-GCM authenticates and encrypts structured task envelopes.
- Sender, recipient, protocol version, timestamp, and message ID are authenticated; stale and
  replayed messages are rejected.
- A shared Wi-Fi network never creates trust. Pairing is accepted only during the desktop's
  time-limited user-opened window and only after code comparison.
- Windows stores its node identity and local secrets through DPAPI. Android encrypts its identity,
  peer records, and voice credentials with Android Keystore.
- Permissions are directional and device-scoped. Capabilities granted to the phone on the PC are
  separate from capabilities granted to the PC on the phone. Revocation removes the grants.

## Voice

Voice is explicitly opt-in. **Voice on** starts Android SpeechRecognizer and enables spoken reply
output. ElevenLabs PCM streaming is used only when a key and voice ID are configured; Android TTS
is the fallback. Barge-in stops current reply playback. **Voice off** and leaving the app stop
speech input/output rather than continuing a hidden conversation.

## Live Vision

Live Vision opens Camera2 only after the user enters its screen and grants camera permission.
Front/rear switching is available, and the UI shows a persistent active-camera indicator. Frames
stay on the phone until **Analyze frame** is pressed, then the selected JPEG is sent through the
encrypted paired-node channel to the desktop's real vision runtime. A failed or unavailable vision
pipeline returns a failure; the Android app does not invent a description.

Remote background camera activation is not enabled. A desktop request for phone camera access must
be approved and completed in the foreground before a frame can be shared.

## Supported Node Tasks

| Direction | Capability | Current behavior |
| --- | --- | --- |
| Phone → desktop | `system.status` | Real CPU, memory, battery, and host state where Windows exposes it |
| Phone → desktop | `chat.complete` | Routes through the selected desktop MORICE model |
| Phone → desktop | `vision.analyze` | Sends an on-demand camera image to the desktop vision runtime |
| Phone → desktop | `application.open` | Resolves, launches, and verifies an installed Windows application |
| Phone → desktop | `media.control` | Uses the Windows media/session control path and verification |
| Phone → desktop | `project.status` | Returns real current workspace/task state; Android has no Project UI |
| Desktop → phone | `device.status` | Battery, charging, platform, and device name |
| Desktop → phone | `media.control` | Android media-key actions for pause/resume/next/previous |
| Desktop → phone | `application.open` | Opens an explicitly named installed package |
| Desktop → phone | `notification.receive` | Displays an authorized MORICE task notification |

File transfer, shared memory sync, Bluetooth transport, internet relay, background photo capture,
and remote screen streaming remain protocol extension points. They are not reported as completed
features in this release.

## Build And Validation

The Android build targets API 36 with a minimum of Android 9 (API 28). The release APK is minified,
resource-shrunk, signed with a dedicated MORICE Android key, and verified with Android `apksigner`.
Lint, debug APK, release APK, instrumentation APK compilation, JVM test discovery, protocol unit
tests, and desktop encrypted-loopback tests are release gates.

No compatible physical Android device was attached during this build. The installed x86_64
emulator image could not boot because the host lacks the Android Emulator hypervisor driver.
Therefore camera, microphone, Android Keystore, installation, foreground-service, and real
phone↔desktop pairing behavior still require physical-device QA; the release does not claim those
runtime checks passed.

## Future Relay

The common protocol keeps transport separate from task schemas so an optional end-to-end encrypted
internet relay can be added later. Local LAN use remains independent of a cloud service, and VOX or
other production services are not migrated by this Android release.
