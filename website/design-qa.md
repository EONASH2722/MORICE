# MORICE visual QA — 2026-11-02

final result: passed

## Scope and intended adaptations

Reference: https://www.moonshot.ai/. The user requested its website idea, animations, and cursor, customized for MORICE, with the typing bar removed. This is a MORICE product website rather than a reproduction of Moonshot's branding or content.

Expected differences: MORICE logo/copy, violet eclipse rim, actual native app screenshots instead of Moonshot research/doodle imagery, six MORICE workspaces, current MORICE release destinations, and no chat input. The hero uses an original live WebGL implementation of the observed moving refracted wordmark and eclipse; it does not load Moonshot's proprietary animation runtime or analytics.

## Visual evidence

Local evidence root: `D:/MORICE/output/playwright/`.

- Source desktop truth: `D:/MORICE/.playwright-cli/page-2026-11-02T10-00-34-802Z.png`.
- Source mobile truth: `D:/MORICE/.playwright-cli/page-2026-11-02T10-02-07-487Z.png`.
- Source cursor hover: `D:/MORICE/.playwright-cli/page-2026-11-02T10-01-52-731Z.png`.
- Source showcase: `D:/MORICE/.playwright-cli/page-2026-11-02T10-03-08-693Z.png`.
- Implementation hero: `morice-desktop.png`, `morice-mobile.png`.
- Same-input side-by-side comparisons: `comparison-desktop.png`, `comparison-mobile.png`.
- Focused cursor comparison: `comparison-cursor.png`; equal 120 × 120 px source/implementation crops enlarged together 3× for inspection.
- Supporting rendered states: `morice-explore.png`, `morice-workspace.png`, `morice-principles.png`, `morice-download.png`, `morice-footer.png`, `morice-full-page.png`, `morice-mobile-menu.png`, `morice-mobile-workspace.png`, `morice-mobile-download.png`, `morice-reduced-motion.png`, `morice-webgl-fallback.png`.

Desktop viewport and screenshot: 1440 × 1000 CSS/pixel dimensions, device scale 1. Mobile viewport and screenshot: 390 × 844 CSS/pixel dimensions, device scale 1. No density normalization needed. Desktop comparison is 2880 × 1000; mobile comparison is 780 × 844. The mobile implementation was additionally captured with `isMobile` and `hasTouch` enabled. Source captures used a desktop browser resized to the same mobile viewport. Hero frames differ because the scenes move continuously. Final screenshots wait for the hero's entrance transition and selected panels to settle.

## Findings and comparison history

1. Initial hero review: the texture had excessive empty space between wordmarks and the initial phrase was offset from the eclipse. Increased texture text width and centered the texture coordinates. The final desktop/mobile comparisons show the moving refracted text passing across the eclipse as intended. Resolved.
2. Paused workspace review: a newly mounted panel could freeze at its entrance animation's low-opacity frame. Disabled the panel entrance animation while paused. Verified all six selected panels and screenshots remain fully visible with motion paused. Resolved.
3. Initial mobile captures were taken during entrance fades. Recaptured after computed opacity reached 1 and after tab transitions completed. This was a capture-state issue. Final comparison uses settled frames.
4. Final combined desktop/mobile comparison and focused cursor review: no actionable P0/P1/P2 findings remain. The source's composer is intentionally absent. The monochrome composition, airy spacing, rounded outline controls, and ring/dot behavior carry through the MORICE adaptation.

## Required fidelity surfaces

- **Fonts and typography:** M PLUS 1 variable headings match the reference family, with system sans-serif navigation/body. Local Latin subset preserves weight variation. Inspected heading hierarchy, line height, wrapping, and letter spacing at desktop/mobile widths. No clipped copy.
- **Spacing and layout:** same 1280 px maximum content span and broad black margins on desktop; stacked cards, wrapped workspace tabs, and stacked downloads on mobile. No horizontal overflow at 320, 390, 768, 1024, or 1440 px. Rounded cards and outlined pills follow the source treatment. Composer removal and MORICE-specific sections are intentional.
- **Colors and tokens:** black background, gray secondary text, white primary text; restrained MORICE violet replaces the source's white eclipse rim. Selection, focus, and active tabs use consistent violet. Native screenshots retain their original colors.
- **Image quality and assets:** existing MORICE logo and real native screenshots are used directly, with preserved aspect ratios in the workspace viewer. Phosphor is the consistent icon family. The live hero is the requested interactive animation, not a substitute raster product image. No hotlinked Moonshot assets, fake app screenshots, or copied remote animation scripts.
- **Copy and content:** standalone MORICE language, verified 0.12.0 Windows release and separate 0.8.0 Android release, accurate local runtime/model requirements. Documentation and repository destinations resolve to the existing project.

## Interaction and runtime checks

Production build and TypeScript validation passed. Package audit reports zero vulnerabilities.

- No text input, textarea, or contenteditable composer.
- Canvas frames change when enabled and remain identical when paused.
- Cursor follows mouse, expands on links, and yields to keyboard and reduced motion.
- Touch context reports coarse pointer and `display: none` for the custom cursor.
- Core, Projects, Research, Spatial, Media, and Security Lab tabs update the correct image and copy.
- Arrow keys, Home, and End move selection and focus correctly.
- Feature cards select their corresponding workspace.
- Mobile navigation opens, closes after section selection, and Escape returns focus to its trigger.
- Every internal anchor resolves; no loaded image is broken.
- Reduced motion starts paused with native cursor and visible content.
- WebGL-unavailable context shows the readable MORICE heading.
- No page errors or browser console errors observed during the acceptance run.

## Implementation checklist

- [x] Desktop/mobile visual comparison and focused cursor comparison inspected.
- [x] All P0/P1/P2 findings resolved and recaptured.
- [x] Primary interactions and graceful fallbacks checked in a real browser.
- [x] Existing GitHub Pages workflow and relative build paths preserved.

Residual limits: browser/device emulation does not certify every physical GPU or phone. The live shader recreates the reference's visual idea; its frames are not identical to Moonshot's scene.
