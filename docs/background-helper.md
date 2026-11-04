# Background Helper

Background Helper keeps MORICE available while the main window is hidden. Say **MORICE**, or hold the middle mouse button and draw around something on screen, to open the same compact assistant at the top of the display.

The popup uses MORICE's existing animated orb, speech input, reply pipeline and voice provider. It does not start another chatbot or leave a permanent orb on the desktop.

## Enable it

Open **Settings → Background Helper** and enable the helper. Choose the shortcuts you want:

- **MORICE wake phrase:** requires the existing microphone permission and a working configured input device.
- **Middle-mouse circle selection:** requires its own opt-in and screen-capture consent.
- **Run after closing the main window:** X hides the main window when a working system tray is available. Use the tray to reopen MORICE or quit it completely.

The helper, wake shortcut and selection shortcut are off by default in a new profile. Automatic explanation and Windows startup are separate options. Installing an update does not grant microphone or screen-capture permission.

If Background Helper is missing from the settings list, quit an older resident copy and launch the updated application. A second launch can raise the already-running instance instead of loading the newly installed executable.

## Use the popup

Say the wake phrase, wait for listening to start, and ask a question. You can also type in the footer and press **Enter**.

The upper-right **Pause/Play** button pauses or resumes the current interaction. Pause stops active listening, response generation and playback while retaining the selected content and answer. The tray has separate pause controls for wake listening and the circle shortcut.

Press **Esc** to dismiss the popup, or use the configurable automatic hide timer. **Ctrl+Shift+C** copies the answer. The compact surface has no close or expansion arrow buttons; open the full application from the tray.

The popup uses a small instance of the existing orb, a curved top-edge panel and a quiet input row. In **Settings → Background Helper → Popup material**, choose transparent black Glass or the more opaque reference-dark material. Reduced Motion disables the slide transition.

## Select content on screen

Hold the middle mouse button, draw a closed loop around the content, and release. A short click remains an ordinary middle click. Drawing starts after a brief hold and movement threshold; tiny scribbles, open arcs and loops spanning monitors are rejected.

After the selection outline fades, MORICE captures one bounded region and masks away pixels outside the enclosed shape. Ask about that selection or enable automatic explanation. Follow-up questions reuse that original image until the popup is dismissed; they do not take another screenshot or activate the camera.

Held middle-button gestures reserve the button. Add applications that need native middle-button dragging to the exclusion list, or pause the circle shortcut from the tray. The helper can also pause for fullscreen applications.

## Speech and models

The small Vosk model supports wake detection and live partial text. Optional local Whisper recognition refines the recorded question before submission. MORICE prefers an installed **faster-whisper-large-v3-turbo** model, then the existing Small option; an explicitly selected compatible model path takes precedence.

The Windows distribution includes the decoder libraries, including Faster Whisper and its VAD data. **Whisper weights are separate downloads**, not included in the installer or portable archive. The standard Turbo checkpoint is approximately 1.6 GB; Small is approximately 486 MB. Select a compatible CTranslate2 model directory under **Settings → Voice → Speech recognition quality**. Recognition runs locally on CPU with INT8 computation and does not download weights during a question.

Accuracy and latency depend on the microphone, background noise, CPU load and whether the decoder is already warm. Whisper can still mishear speech. Diagnostics distinguish live text, the refined transcript and an unavailable accuracy engine. Recognition and model failures are reported rather than replaced with fabricated replies.

Reply audio uses the existing Voice settings. A configured ElevenLabs provider retains its selected voice and model. Windows local speech remains an option; fallback follows the user's existing setting. This feature does not install a new voice or embed an API key in the application.

## Main application Glass theme

Choose **Theme → Glass**, or **Settings → Appearance → Theme → Glass**, for near-black panels with the desktop visible through the main window. Increase **Advanced appearance → Glass intensity** to reveal more of the background. High contrast and the opaque themes restore full opacity.

The main theme uses native whole-window translucency, so its text and controls also become translucent. The popup uses per-pixel alpha. These are transparency effects; native frosted desktop blur is not implemented. The existing Blur control softens the decorative field inside MORICE.

## Privacy and lifecycle

- Wake listening, global selection and capture each follow the existing permission and preference controls.
- Selection captures remain in memory, are discarded on dismissal, and are not continuously collected while idle.
- Selected images use the existing local vision provider. This feature adds no cloud image upload; a separately configured speech provider follows its own existing service behavior.
- Known protected applications and Windows-protected surfaces are excluded where detectable. This is not complete detection of sensitive fields inside arbitrary websites or applications.
- One helper owns the tray, popup, selection hook and wake listener for the shared runtime. Additional MORICE windows reuse it.
- Quit releases the helper's hooks, listener and windows through the existing runtime shutdown. Closing without a usable tray retains normal shutdown behavior.

## Validation and limits

Automated coverage exercises geometry, masking, consent, one-capture follow-ups, cancellation, stale results, shared ownership, settings search, pause/resume, popup alpha, theme switching and shutdown. Packaged decoder tests use synthesized PCM and real local recognition; they do not establish physical microphone accuracy in a room.

Physical wake-and-question use, middle-button gestures in individual applications, elevated applications, fullscreen games, sleep/resume and real mixed-DPI multi-monitor hardware require hands-on acceptance. Software coordinate tests do not certify that hardware behavior. Local vision and language models can produce inaccurate explanations; review consequential answers against the selected source.
