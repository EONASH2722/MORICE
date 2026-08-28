# Troubleshooting And FAQ

## Installation And Launch

### MORICE does not start

- Extract the portable ZIP fully; do not launch from inside the archive.
- Keep `MORICE.exe` and `_internal` together.
- Verify all parts and `checksums.json` came from the same release.
- Install current GPU drivers and the Microsoft Visual C++ runtime.
- From source, use Python 3.12+ in a clean virtual environment.

### The taskbar icon or title is wrong

Use the current packaged `MORICE.exe`, not an older `dist` folder or pinned shortcut. Remove the old shortcut, rebuild/pin the current executable, and restart Explorer if Windows still caches old metadata.

### Maximized content is cut off

Reset interface scale and workspace layout in Settings. Verify Windows display scaling, then reopen MORICE. Use the standard title-bar maximize button rather than forcing fullscreen through another utility.

## Models And Replies

### MORICE returns no text

Empty completions are converted into a visible failure. Retry once, reduce prompt/context size, close VRAM-heavy programs, inspect logs, or choose another model. A blank model response is never counted as completed work.

### A long answer stops early

Keep the app open until the background status returns to idle. If the model ended at its token limit, ask `continue from the last complete section` or choose a model/context plan with more headroom.

### MORICE identifies the wrong model

The authoritative source is the active-model status and model manager, not the model's self-description. Local models can hallucinate their identity; MORICE's host prompt instructs them not to do so.

### Can I use a hosted API?

General hosted LLM-provider configuration is not integrated. Model inference remains local GGUF/Ollama. ElevenLabs is supported only for optional text-to-speech and its key is stored with Windows DPAPI or supplied through the ignored local `.env` file.

## Visualization

### Visualization unavailable

No validated widget was mounted. Read the card for an unsupported family, parse error, invalid topology/data, missing file, size limit, or runtime error. Add an explicit renderer type, equation, molecule name, numeric values, units, or valid local path.

### The wrong renderer opens

Use explicit language: `plot`, `simulate`, `render the curated molecule`, `visualize the data structure`, `chart these values`, `draw a flow diagram`, or `preview this local file`. Router tests prevent common dashboard labels from hijacking time/date or file-preview intent, but ambiguous prompts can still need clarification.

### Why does an unknown molecule fail?

Chemistry rendering uses a curated validated structure library. MORICE refuses to invent atom positions for an unknown molecule. General cheminformatics generation is not part of this release.

### Is every 3D schematic dimensionally accurate?

No. Supported component scenes are labeled educational. Numerical graphs and supported physics parameters have stronger accuracy tests; generic schematics are not manufacturing CAD.

## Project Mode

### No files were written

- Select a work folder with `+`.
- Do not select the MORICE installation folder.
- In folder-limited mode, wait for the proposed manifest, review the diff, and press Apply.
- In Full access, routine validated project files are written atomically and the diff becomes an audit view. Confirm the reply says the write was verified.
- Keep folder-limited paths under the selected root.
- Check Project output for invalid JSON, model timeout, missing toolchain, or test failure.

### MORICE built a page instead of the requested game/app

State `create the complete playable application, not a landing page`, name the framework, list required mechanics, and include a runnable acceptance test. Use a coding-focused model. The local fallback builder is narrower than the model-driven project path.

### The review panel will not close

Use the close control on Project changes/Lab, then reset the workspace layout if it remains pinned. The current build includes a regression test for closing Lab during splitter transitions.

## Voice

### Wake phrase is missed

```powershell
python diagnose-wake-listener.py
```

First enter **Mode > Live Action**. Grant Windows microphone permission, choose the intended input, reduce competing background audio, and recalibrate. Adaptive gain and noise-floor learning improve weak microphones but cannot recover clipped or absent audio. The installed background listener releases its microphone lease while Live Action is active. Disable it with `MORICE_ENABLE_ALWAYS_ON_WAKE=0` or Windows Startup Apps when diagnosing another application's exclusive microphone access.

### Speech input or spoken replies do not work

Enter **Mode > Live Action**, then open **Panel > Live Action voice configuration**. Speech input needs a detected Vosk model, Windows microphone permission, and a working input device. If a saved hardware endpoint is unsupported, select **System default**; MORICE also falls back to the Windows default automatically. ElevenLabs output needs **Speak MORICE replies in Live Action** enabled and a key saved through **Store API key securely**. MORICE never saves the key in `settings.json`; the field clears after storage. The local `.env` template is an alternative for development and must remain untracked. Leaving Live Action intentionally stops camera, microphone input, and spoken output.

Open **Tools > Diagnostics > Voice** and run **Test Microphone**. A detected device plus a changing level confirms capture independently of recognition. The result lists the selected/default endpoint, sample rate, VAD state, and exact backend error; the temporary sample is not retained.

## Android Companion

### The phone cannot pair with the desktop

Keep both devices on a mutually reachable LAN, open **Panel > Pair a device** immediately before
pairing, use the address and port shown by MORICE, and compare the six-digit code on both screens.
Windows Firewall or guest Wi-Fi client isolation can block the LAN socket. Sharing Wi-Fi alone does
not create trust; a pairing request outside the explicit two-minute window is rejected.

### A phone or desktop task is denied

Capabilities are directional. A phone permission does not automatically grant the desktop the
matching operation, and a desktop grant does not automatically grant the phone. Review the paired
device entry and grant only the required capability. Camera sharing remains foreground and
user-initiated even when a vision capability exists.

### Android voice or camera is unavailable

Grant microphone/camera permission in Android settings, return to the foreground, and explicitly
enable **Voice on** or open **Live Vision**. Battery or OEM background restrictions may stop the
connection service. The release build passed compile, lint, signing, and encrypted desktop-loopback
checks, but actual device audio/camera behavior still depends on the phone and was not claimed as
physical-device verified for this release.

### Camera preview or visual answers do not work

Enter **Mode > Live Action** and press **Turn camera on**. If the preview stays unavailable, allow camera access in Windows **Privacy & security > Camera**, close another application that may exclusively own the camera, and reselect the device. Diagnostics > Voice lists the camera state, active device, actual resolution, preview FPS, frame conversion failures, vision-provider state, visual-model name, request latency, last failure, and temporary-memory state. A preview without a visual answer usually means the local visual model is unavailable or the frame failed the darkness, contrast, blur, or freshness gate; MORICE reports the exact condition in the glass overlay.

## Amazon Music

### Amazon Music is installed but MORICE says application not found

Refresh or restart MORICE so its cached Windows application index is rebuilt. The index includes Start apps/Store identities, Start Menu shortcuts, App Paths, PATH, common install locations, and running processes. Confirm **Default music provider** is `Amazon Music`. MORICE should resolve `Amazon Music`, `music`, and `music app` to the Store app identity rather than treating the rest of a compound command as part of the app name.

### A requested track did not start

MORICE only reports a specific-song request as verified when the semantic Amazon search result and the Windows Amazon media session agree on the playing track. Account prompts such as “stream from this device” are handled during an explicit play request. An unnamed playlist remains ambiguous and requires its name. Amazon does not consistently expose playback position, so track restart can be sent without being independently verifiable.

## Performance

### High RAM or VRAM use

Pause/close active visualizations, reduce particle count, close GPU-heavy applications, use a smaller quantization/context, and restart the model runtime after switching large models. The title bar reports current local resource estimates.

### Simulation slows in the background

Hidden physics canvases are designed to stop consuming simulation frames. Report a bug with the exact renderer, particle count, whether Lab was open, and performance diagnostics if usage remains high.

## Diagnostics

```powershell
python -m compileall -q morice
python -m unittest discover -s tests
cd vnext
pnpm test
pnpm run typecheck
```

Use `scripts\build-release.ps1` for release packaging. Do not ship an old local `dist\MORICE` directory.
