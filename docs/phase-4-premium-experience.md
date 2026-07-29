# Phase 4: Premium User Experience

Phase 4 makes the existing MORICE desktop workspace more coherent, responsive,
accessible, and observable. It does not replace the renderer, agent, or desktop
service layers. The same verified graph, simulation, project, file, and tool
components are presented through one shared experience system.

## Experience Architecture

`morice/ui_system.py` owns the shared visual and motion primitives:

- five tokenized themes: Light, Dark, Midnight, Glass, and Custom;
- configurable accent color and bounded panel opacity;
- high-contrast focus rings and consistent interactive states;
- one interruptible animation manager with Slow, Normal, and Fast timing;
- reduced-motion behavior that applies final states immediately;
- button micro-interactions and interruptible smooth scrolling.

`morice/premium_experience.py` owns normalized profiles and workspace layouts:

- atomic profile persistence, import, and export;
- bounded, validated appearance and accessibility values;
- Balanced, Focus, Science, Project, and Research splitter presets;
- a bounded live-chat window for long conversations.

`morice/premium_ui.py` provides searchable settings with category navigation,
live appearance preview, reset controls, profile switching, and profile
import/export.

## Window And Layout

MORICE keeps the custom title bar while preserving standard minimize, maximize,
restore, close, drag, double-click, edge-snap, and multi-monitor geometry
behavior. The title bar now reports:

- active workspace;
- selected local model;
- GPU, RAM, and VRAM usage when available;
- active and queued task count;
- command palette, quick settings, theme, and native window actions.

The main workspace remains one `QSplitter`. Its Mode, Conversation, Science,
Project Review, Personalization, and Tools surfaces are individually
collapsible and resizable. Exact splitter sizes, fullscreen/maximized state,
theme, accent, visibility, recent commands, and the active workspace preset are
saved atomically. Normal launches still begin with a fresh private chat by
design; only explicit crash recovery restores conversation text.

## Chat And Composer

Messages are independent left/right glass bubbles rather than one opaque
transcript panel. Each bubble has:

- local rich Markdown, code, table, and math rendering;
- author, timestamp, copy action, reaction control, and accessible label;
- edit-to-composer for user messages;
- an interruptible reveal and subtle completion highlight.

Only the latest 100 message widgets stay live. Older messages are retained in a
bounded virtual archive and can be progressively restored in batches. This
reduces widget/layout work without changing the model's current conversation
context.

The composer is a multiline auto-expanding editor. Enter sends, Shift+Enter
adds a line, and Up/Down walks recent prompts. Compact controls expose image
attachment, voice/wake status, model selection, chat/project selection, quick
actions, Precision, personalization/access state, and Send. `Ctrl+O` attaches
an image, `Ctrl+K` opens universal actions, and `Ctrl+,` opens settings.

## Settings And Accessibility

The side panel retains the immediately visible name, response style, wake line,
emoji, maturity, and font controls. It now also exposes:

- all five themes;
- animation speed and reduced motion;
- high contrast and large text;
- interface scale from 80% to 160%;
- bounded glass opacity;
- workspace presets;
- the searchable advanced settings window.

All icon buttons have accessible names and tooltips. Keyboard focus gets a
visible accent ring. Scaling is based on one stable application font size so
switching profiles cannot compound text size.

## Renderers And Notifications

Verified renderer cards remain in Normal Chat. Their controls continue to use
the validated artifact or simulation state, never model prose. Graphs,
molecules, diagrams, charts, scenes, and physics can open a separate large
window without blocking chat. Existing 2D/3D selection, reset, pause, replay,
inspect, screenshot, and export controls remain available by renderer.

Notifications support Information, Success, Warning, and Error states, optional
actions, progress, auto-dismiss, and copyable error details. Notification
history remains available in the desktop Tools workspace.

## Performance Contract

- long chats keep at most 100 live message rows;
- renderer preparation remains on bounded workers;
- hardware monitoring runs outside the UI thread;
- scroll and property animations are interruptible;
- reduced motion removes animation work;
- hidden physics canvases remain throttled by the VNext runtime;
- expensive renderer widgets are created only for validated artifacts.

Phase 4 targets responsive 60 FPS interaction. Actual simulation FPS depends on
the selected renderer, particle count, model inference load, display scale, and
hardware.

## Verification

The Phase 4 tests cover profile persistence, normalization bounds, all themes,
focus/contrast CSS, animation timing, reduced motion, adaptive composing,
message controls, layout presets, top-bar status, actionable notifications,
recent commands, and chat virtualization. Existing workspace, project, desktop,
rendering-accuracy, and VNext suites remain part of the release gate.

## Current Limits

- renderer windows detach into non-modal child windows; arbitrary drag docking
  between independent top-level windows is not implemented;
- local model transports that return one complete response cannot expose real
  token streaming, so MORICE shows truthful generation stages instead of fake
  token timing;
- touch momentum depends on the Qt platform plugin and input hardware;
- automatic operating-system theme scheduling is not yet connected to the
  Windows appearance registry.
