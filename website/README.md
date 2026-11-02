# MORICE website

MORICE's React + TypeScript product website, built with Vite and published at https://eonash2722.github.io/MORICE/ through the existing GitHub Pages workflow.

The design adapts the spacious black layout, refracted wordmark animation, pill buttons, reveal transitions, and dot-and-ring cursor observed at https://www.moonshot.ai/. Copy, logo, product imagery, links, and violet accents belong to MORICE. There is no chat composer or typing bar.

## Development

```sh
npm ci
npm run dev
npm run build
npm run preview
```

`npm run build` includes TypeScript validation. Vite's relative base supports GitHub Pages' `/MORICE/` subdirectory. Pushes to `main` that change `website/**` trigger `.github/workflows/pages.yml`.

## Implementation

- `src/App.tsx`: responsive navigation, product sections, six keyboard-accessible workspace tabs, and version-specific release links. Windows is 0.12.0; the separate Android companion remains 0.8.0.
- `src/HeroScene.tsx`: an original WebGL eclipse and refracted moving MORICE wordmark. The scene responds to the mouse and stops when hidden, offscreen, or paused. A semantic text heading remains available if WebGL is unavailable or lost. There are no remote animation scripts.
- `src/CustomCursor.tsx`: a 5 px dot and trailing 36 px ring that expands to 56 px on links and buttons. It is enabled only after a real mouse event on a fine pointer. Touch, keyboard use, and reduced motion retain the native cursor. Cursor updates do not rerender React.
- `src/styles.css`: responsive layouts, focus states, scroll reveals, hover states, and reduced-motion behavior. Manually pausing motion also keeps newly selected workspace panels fully visible.
- `public/`: the existing MORICE logo and actual desktop screenshots. The M PLUS 1 Latin variable font is served locally; its license and provenance are in `public/fonts/`.

The page is a product overview. It does not run inference or access the microphone, camera, or files. Compatible local runtimes and model weights are separate app requirements.

## Validation

The production build was checked in Chromium at 1440, 1024, 768, 390, and 320 px widths, plus a touch-enabled mobile context. Checks covered animation/pause, cursor hover, all workspace tabs and images, keyboard navigation, mobile menu and Escape, section anchors, release destinations, reduced motion, WebGL fallback, console errors, and horizontal overflow. See `design-qa.md` for the visual comparison and evidence paths.
