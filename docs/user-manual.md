# MORICE User Manual

This guide describes the 0.9.4 desktop. For the shortest file-building and experiment walkthrough, use [Projects and Experiments](simple-workspaces.md).

For online places, distance questions and image generation without references, use [Locations and prompt-only images](spatial-media-0.9.4.md).

## Install

### Earlier 0.8.0 installer

No new 0.9.4 installer is included. Use the current portable ZIP or Python package below for this update.

Keep `MORICE-Setup-v0.8.0-Windows-x64.exe` and all numbered installer `.bin` slices from the same release together. Run the setup executable and launch MORICE from the installed shortcut.

### Portable

Download `MORICE-Portable-v0.9.4-Windows-x64.zip` from the [0.9.4 release](https://github.com/EONASH2722/MORICE/releases/tag/v0.9.4), verify its SHA-256 against the accompanying checksums, and extract it. Launch `MORICE.exe` from the extracted folder; keep `_internal` beside it. Large language and generative model weights are installed separately. Earlier multipart 0.8.0 packages require all their matching parts and their reassembly script.

### Python package

The wheel is a model-free advanced installation. Install the downloaded `morice_ai-0.9.4-py3-none-any.whl` with `python -m pip install <wheel-path>`, then run `morice`. Configure a local GGUF or Ollama model in the application. This release does not claim a public package-manager channel until publication is independently verified.

### Android companion

Download `MORICE-Android-0.8.0-android.apk` and its JSON manifest from the Android
release. Verify the SHA-256 value, install it on Android 9 or newer, then use **Devices** on the
phone and the **Devices** workspace on the desktop. Compare and confirm the same six-digit pairing
code on both devices. Pairing is explicit, time-limited, encrypted, and grants capabilities in each
direction separately. See the [Android companion guide](android-companion.md).

## First Launch

1. Start MORICE and open **Chats** to send a normal message.
2. Open **Settings → Personalization** to choose how MORICE addresses you.
3. Use **Theme** in the top bar for visual themes and motion, and Settings for font, contrast and scale.
4. Open **Settings → Models** to select an installed GGUF or Ollama model and inspect hardware fit.
5. Open **Projects** when you want files created or edited, **Research** for supported experiments, or **Voice** for Live Action.

MORICE opens with a clean visible conversation. Durable memory, project records, and platform data are separate services and do not repopulate the chat transcript.

## Normal Chat

Type a message and press Enter or **Send**. The Send button remains disabled while the input is empty or a non-steerable action is active. During a long local completion, the composer can queue or steer a follow-up instead of creating overlapping replies.

- **Attach:** selects supported files for context.
- **Microphone:** enters or exits the Voice/Live Action workspace.
- **Context:** reveals project/model context controls when needed.
- **Projects:** selects the file-building workflow; use Build or Ask within that workspace.
- **Settings:** configures models, personalization, voice and appearance.
- **Search · Ctrl K:** finds commands and additional controls.

Use explicit nouns, values, and units. MORICE corrects common spelling errors using conversation context, but precise requests improve local-model results.

## Visualizations In Chat

Visualization is available in Normal Chat and Live Action, not in the dedicated Project Mode conversation surface.

```text
Plot y = x^3 - 6x^2 + 9x + 15 and mark its extrema.
Render an interactive Mandelbrot set.
Simulate a double pendulum with g = 9.81 m/s^2.
Render the curated benzene molecular model in 2D and 3D.
Visualize a BST and demonstrate insert, search, and delete.
```

The request moves through analyzing, renderer selection, data preparation, validation, and mounting. A successful progress card is replaced by a real interactive widget. A failure card states that nothing was rendered and gives the parser/validator error.

Controls vary by family: zoom, pan, rotate, hover inspection, 2D/3D switch, pause, resume, step, reset, time scale, vectors, trails, labels, parameter inputs, and export. See the [feature matrix](feature-matrix.md) for exact coverage.

## Project Mode

1. Open **Projects**, then **Choose folder** and select a work folder outside the installation.
2. Keep **Build or edit files** selected and describe a concrete, bounded change.
3. Select **Build files**. In folder-limited mode, inspect **Review**, then select **Save reviewed files** or **Discard proposal**.
4. Inspect actual source under **Files**, checks and errors under **Output**, and replies under **Updates**. Web previews appear in **Preview**.
5. Use **Ask about this project** for explanations without file changes. **Build settings** contains access and lookup controls.

The [Projects and Experiments guide](simple-workspaces.md) explains the shared task/output limits and unavailable toolchain behavior. Large applications should be developed through smaller changes.

MORICE asks the coding model for file artifacts rather than instructions to copy and paste. Invalid or unsafe project JSON cannot replace existing files. Read the full [Project Mode guide](project-mode.md).

After a change, **Show process** remains available. It records detected project type and tools,
the exact files found on disk, real build/test commands, exit codes, and verification results. A
file-only result, unavailable editor, skipped playtest, and successful runnable build are distinct
states; MORICE does not label them all “done.”

## Experiments

1. Open **Research → New experiment**.
2. Describe a supported experiment with values and units, or choose a model and enter values in the form.
3. Select **Review experiment** and inspect its actual inputs, limits and planned run count.
4. Select **Run experiment**, then open **Results** for stored numerical outputs.

The guided form supports driven oscillators, thermal expansion, ideal mixture density and vacuum particles. Missing inputs remain visible in Research; no chat fallback invents an experiment. **Notebooks** and **Advanced** reveal the existing stored projects and technical controls. See [Projects and Experiments](simple-workspaces.md) for sweeps and concrete limits.

## Android Companion

The phone app keeps one unified chat and adds opt-in voice, on-demand Live Vision, device status,
media control, and application launch. Desktop Project Mode is intentionally not copied to the
phone. Phone requests use the paired desktop model and tools only when the corresponding capability
is granted. Voice stops when toggled off or when leaving the app; the camera opens only in Live
Vision after foreground permission, and a frame leaves the phone only when **Analyze frame** is
pressed. Remote background camera activation is not enabled.

## Tools Workspace

**Tools** opens a resizable workspace with:

- Dashboard;
- file explorer and downloads;
- activity timeline, tasks, logs, and clipboard;
- platform memory, automations, diagnostics, recovery, updates, and plugins;
- system status, notes, browser context, media, and permission-controlled desktop actions.

Ask naturally. MORICE retrieves relevant local notes automatically, recognizes when an answer depends on current information, and uses source-linked web context when connectivity is available. If the network is unavailable, it stays on the local path and says when freshness could not be verified.

## Amazon Music And Fast PC Commands

Amazon Music is the default music provider in this build. Change it in **Panel > Mode > Default music provider**; generic phrases such as `open music`, `play music`, and `play Starboy` use that setting.

Routine commands route directly to validated local tools and do not start the conversational model. Amazon Music is discovered from the Windows application index, launched as a Store app, searched through semantic accessibility controls, and verified against the Windows media session. Supported direct commands include song/artist search and play, pause, resume, next, previous, current-track metadata, system volume adjustments, exact volume percentages, open, and close. `Restart this song` sends the best available Amazon/Windows transport command, but Amazon does not expose playback position on every session, so MORICE reports it as unverified when the reset cannot be measured. An unnamed `play my playlist` asks for the playlist name instead of guessing.

## Model Selection

The current release supports validated local GGUF files and locally installed Ollama models. The model browser can detect GPU memory, estimate compatibility, display source/license metadata, and prepare a run plan. Hosted LLM keys are not configured; the separate ElevenLabs key control is only for optional reply speech and stores the secret with Windows DPAPI.

Changing the model changes reply and coding quality; it does not bypass host rendering, path, or permission checks. See [Models and performance](model-guide.md).

## Appearance And Personalization

- **Theme:** use the exposed Glass/dark/light appearance paths.
- **Font:** choose a bundled family or load a local `.ttf`, `.otf`, or `.ttc` file.
- **Emoji amount:** none, medium, or higher-use model prose.
- **Maturity:** adjusts wording tolerance, not factual standards or safety boundaries.
- **Motion:** select an animation profile or reduce interface motion.
- **Accessibility:** high contrast, larger UI text, interface scale, and layout profiles.

The top-bar sun/moon control switches the active theme. Settings includes search and live preview.

## Desktop Pets

Open **Panel > Desktop companion**, enable **Show desktop pet**, then choose Iron Man — Mark 42, Spider-Man, Horse, Skeleton, Dog, or Cat. Size and animation speed are independent of the main interface motion setting. **Pet click action** defaults to **Open MORICE** and can instead open chat directly or do nothing.

Use **Pet special events** to select Off, Low, Normal, High, or Showcase. Normal keeps armor-off, symbiote, enemy fights, fetch, deep sleep, grazing, and collapse/reform scenes rare; Showcase makes them appear within seconds for a demo. Cooldowns persist across restarts and scenes stop cleanly if you grab the pet or enter fullscreen.

A short primary-button press plays the character's reaction and immediately restores, raises, and focuses the existing MORICE window. If MORICE is not running, one new instance is launched. Moving beyond the Windows/Qt DPI-aware drag threshold changes the gesture into a pet interaction and cannot open MORICE on release. Rapid clicks are coalesced by the launcher and MORICE's per-user single-instance endpoint.

Leave **Hide pet during fullscreen/games** enabled to remove both the overlay and its click target while another application owns a fullscreen monitor. MORICE returns the pet afterward. A restored MORICE window keeps its previous valid monitor position; it is moved only when that display no longer exists. **Remove Pet** stops the resident host and disables the setting.

See the [desktop-pet guide](desktop-pets.md) for behavior details and transparent animation/screenshots.

## Live Action Mode

Open **Voice → Live Action**, or press the microphone button beside the chat composer. Entering Live Action also wakes MORICE, so no second wake phrase is required. MORICE starts offline Vosk transcription, auto-sends the recognized turn when configured, streams an ElevenLabs reply when reply speech and a key are configured, and then resumes listening. Live Action replaces chat bubbles/history with a camera-centered workspace, a live transcript, a glass streaming-response overlay, and its own typed composer. Chat, graphs, Lab, Tools, attachments, PC control, and Project build requests still use their normal pipelines.

The camera remains off until **Turn camera on** is pressed. Select the camera, resolution, FPS, and mirror setting in the Live Action toolbar. Preview frames remain in memory and are never recorded to disk. Vision runs on the newest real frame only after a visual request such as “What am I holding?” The optional **Scene awareness** toggle tracks only lightweight scene changes; it does not run the visual model continuously. Low-quality, stale, missing, or unavailable frames produce an explicit failure instead of a guessed answer. Provider-supported normalized regions may be drawn on the preview; MORICE does not fabricate targeting boxes.

Use **Exit Live Action**, select **Normal chat** in Voice, or press the active microphone button again to leave. Leaving stops the camera, microphone capture, speech playback, and pending vision work immediately; it clears raw frames and short-lived visual memory and ignores late callbacks. MORICE intentionally starts outside Live Action after every launch.

Set the wake line and audio devices in **Settings → Voice**. Microphone quality is improved through adaptive gain, noise-floor calibration, default-device fallback, and diagnostics, but Windows microphone privacy permissions and actual hardware still matter. ElevenLabs is optional for reply speech; without a configured key, the glass text response still works.

Open **Tools > Diagnostics > Voice** to inspect the selected/default input device, supported sample rate, input level, VAD activity, partial/final transcript, confidence availability, and recognition latency. **Test Microphone** captures a short temporary sample, optionally plays it back, and discards the audio immediately.

```powershell
python diagnose-wake-listener.py
```

Background microphone wake is off by default. Live Action only uses the microphone after you enter that mode. If you deliberately want local wake-word or double-clap detection while MORICE is closed, set `MORICE_ENABLE_ALWAYS_ON_WAKE=1` before starting `MORICE.exe --morice-wake-listener`; it starts MORICE minimized without stealing foreground focus and releases its microphone lease while Live Action is active. It never turns on the camera.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Enter` | Send from the active composer when enabled |
| `Ctrl+K` | Command palette / quick actions |
| `Ctrl+O` | Attach an image |
| `Ctrl+,` | Open settings |

## Privacy

Local GGUF/Ollama inference, deterministic rendering, notes search, project work, and local memory can remain on the machine. Online+local and web lookup intentionally access network sources. Plugins have declared permissions and run outside the main process, but users should still install only trusted packages.
