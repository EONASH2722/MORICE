# MORICE 0.11.0 — holographic interface and chat thinking controls

MORICE's globe and interface now share one surface. The original logo, model profiles, conversations, tools and permissions remain in place.

- A large native GPU globe materializes from light at cold startup. Independent 3D orbits, filaments, particles and wire structures continuously animate.
- Pointer proximity, hover, click ripple, drag inertia, double-click reset and smooth wheel/touchpad zoom remain available during generation. The animation eases between idle, interaction and actual work.
- White, Pitch Black and Glass cover the app's pages, native menus/dialogs, scientific neutral backgrounds and rich responses. Globe light and surrounding glow remain independently selectable in every theme.
- Model thinking levels are in the chat composer: Low, Medium, High and Extra high. Higher levels use the selected thinking model and larger bounded reasoning/output budgets. Low preserves fast model routing.
- An expandable activity view reports actual preparation, source search, page reading, model loading, reasoning-token activity and writing. Supplied text/HTML links become untrusted source context, with real failure reporting. It does not fabricate task stages or show model prose as verified reasoning.
- Wake activation opens chat in the selected theme while preserving existing voice permissions, transcript review and fullscreen behavior.
- Voice mode removes the editor and answer-text overlay. The globe follows real speech playback amplitude; microphone and optional camera controls remain available.
- Selecting a rich-result section after compact-window layout changes brings its header into view, while later user scrolling cancels the pending adjustment.

The preferred installed reasoning model remains `Qwen3.5-4B-abliterated.Q6_K.gguf`. Weights are separate; explicit model selections are preserved. Increased effort is a budget setting, not a guarantee of correctness. The primary finite reasoning budget is supported by the bundled llama.cpp server; other providers retain their adapter-specific limits.

Extract the portable ZIP fully, or keep Setup and its matching `.bin` file together. Verify downloads using `SHA256SUMS.txt`. See the [guide](globe-interface-0.11.0.md) and [validation report](globe-validation-0.11.0.md) for exact checks and limitations.
