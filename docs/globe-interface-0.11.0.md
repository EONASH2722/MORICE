# Globe interface

The home screen and chat share one GPU renderer rather than a separate globe panel. The geographic Earth in Spatial Lab is still a different scientific feature. The MORICE logo is unchanged.

Choose **White**, **Pitch Black** or **Glass** from Theme or Settings → Appearance. Glass uses translucent application materials and native window opacity; it does not capture or reconstruct desktop contents. Historical appearance files remain readable.

Move the pointer near the globe to disturb its local light field. Click for a ripple, drag to rotate with inertia, scroll or use a precision touchpad to zoom, and double-click to reset the view. Arrow keys rotate; plus/minus zoom when the globe has focus. Scrolling over chat continues scrolling the conversation. Idle motion yields smoothly to pointer interaction; real generation activity and pointer effects can run together.

Cold startup reveals the energy core, particles, wireframe, orbit families and glow over approximately three seconds. Escape or Skip finishes the visual introduction without interrupting services. Minimize/restore, navigation and color changes do not replay it. Required service failures never produce a ready label. Language model loading remains on demand. If OpenGL cannot initialize, an explicitly labelled reduced-quality fallback leaves the app usable.

**Globe Color** and **Globe Glow Color** are separate controls. Their dialogs preview changes immediately without rebuilding geometry or restarting animation; Cancel restores the previous channel. Both selections are stored through the existing appearance store.

**Model thinking** is in chat, outside Settings. Low preserves automatic fast routing and allows up to 256 reasoning tokens when the thinking backend is used. Medium, High and Extra high select the reasoning profile and allow up to 1,024, 2,048 and 4,096 reasoning tokens respectively, with answer room reserved. Output/context limits can further reduce those caps. The choice is captured for the next request, so changing the dropdown does not alter a request already running. Provider/model capabilities still determine the result.

Expand **Thinking / Show activity** to inspect public execution receipts. Opening/reading a link is shown only during an actual bounded HTTP request and extraction. Source failures remain visible. Model thinking is shown when the backend emits reasoning-token activity, without copying raw reasoning into the UI as verified evidence. Normal answers remain text unless an interactive result is warranted or requested.

The page reader accepts at most three explicitly supplied HTTP(S) text/HTML/JSON resources, at most 2 MB each, and extracts bounded text. It does not bypass login, anti-bot protection, JavaScript-only rendering or unsupported PDF/video formats. External page text is passed as untrusted source material. Existing browser/research/media tools remain available for their supported formats.

Reduced Motion skips the cinematic introduction and decorative particles/rotation while preserving deliberate drag, zoom and readable feedback. Rendering pauses when minimized and reduces its cadence under model/media/GPU pressure. See the [validation report](globe-validation-0.11.0.md) for measured performance and limits.

Voice mode uses the globe instead of a text entry field or on-screen answer overlay. Its pulse follows actual speech output amplitude with smoothed attack and release; idle motion returns after playback. Existing microphone, speech-provider and camera preferences still apply. Disabled or unavailable speech is reported by its existing status controls; the UI does not invent a speaking waveform. Return to Chats for typed input and retained messages.
