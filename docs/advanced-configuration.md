# Advanced Configuration

## Appearance And Accessibility

Open **Settings** for searchable categories and live preview, or use the compact **Panel** controls.

- Theme: Glass, dark, and light-capable appearance paths exposed by the current build.
- Accent and opacity: color selection and glass opacity without reducing text opacity.
- Font: bundled choices plus local `.ttf`, `.otf`, or `.ttc` files.
- Emoji amount: none, medium, or higher-use response styling.
- Maturity: controls allowed wording style; it does not remove factuality or safety controls.
- Motion: animation profile and reduced-motion mode.
- Accessibility: high contrast, larger UI text, interface scale, and layout profile.

Custom font files remain local. Use a font license that permits your intended use.

## Conversation Configuration

Personalization stores:

- how MORICE addresses the user;
- response-style instructions;
- wake phrase;
- presentation options.

These settings influence the model prompt but do not override renderer validation, project boundaries, or sensitive-action confirmation.

## Inference Tuning

The main practical controls are model size/quantization, context length, GPU layers, and provider choice. Start conservatively, verify stability, then increase context or offload. Watch the title-bar GPU/RAM/VRAM indicators while generating.

For a 6 GB mobile GPU, close games and GPU-heavy browsers before loading the release model. Windows display allocation means not all advertised VRAM is available to inference.

## Knowledge And Memory

MORICE selects relevant local knowledge automatically when a request overlaps indexed notes. It also detects freshness-sensitive questions and uses source-linked web context when connectivity is available; offline requests remain local. Memory services are scoped, searchable, bounded, and exportable. They are separate from the visible chat, which starts clean on a new application session.

The packaged background wake listener is enabled by default and remains local. Set `MORICE_ENABLE_ALWAYS_ON_WAKE=0` to disable it. The listener recognizes the saved wake terms and double-clap pattern, starts MORICE minimized, never enables the camera, and yields microphone ownership to an active Live Action session.

Do not place secrets in notes, project prompts, or plugin data unless the relevant local storage and plugin permissions have been reviewed.

## Performance Profiles

- Enable reduced motion on integrated graphics or remote desktop sessions.
- Pause simulations when they are not being inspected.
- Close hidden Lab/workspace panels to release render scheduling work.
- Prefer smaller particle counts on CPU-only systems.
- Use local mode when current web context is unnecessary.
- Keep project snapshots focused; very large generated/vendor trees add indexing cost.

## Diagnostics And Recovery

Tools exposes health, logs, performance, agent, and component information. The platform services also support recovery records, backups, update checks, and restore workflows. Capture diagnostics before restarting when reporting intermittent model or renderer failures.
