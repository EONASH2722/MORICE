# MORICE VNext Science Workspace

This document defines the VNext direction for turning MORICE into a scientific AI workspace while keeping the current desktop app stable.

## Current Desktop Slice

Implemented in the Python/PySide app:

- `morice/science_engine.py`
  - Parses safe math expressions.
  - Generates deterministic graph samples.
  - Supports standard function plots, multiple equations, polar curves, and parametric curves.
  - Emits graph inspection points for x-intercepts, y-intercepts, and extrema when available.
  - Generates deterministic 2D particle/projectile simulation state.
  - Emits model-agnostic instructions using `simulationType`, `equations`, and `parameters`.
- `morice/pyside_app.py`
  - Adds a collapsible `Lab` workspace dock.
  - Shows graph and simulation preview cards in chat.
  - Opens actual visualizations in the Lab dock, not inside chat.
  - Supports graph zoom, pan, point inspection, intercept callouts, extrema callouts, and multiple equations.
  - Supports physics pause, resume, step, speed control, and live stats.
  - Keeps normal focus behavior predictable by avoiding automatic input focus after background replies finish.

## Future TypeScript Engine Layer

Scaffolded in `vnext/`:

- Strict TypeScript.
- Plotly for production graph rendering.
- MathJS for expression parsing and validation.
- Matter.js and Planck for richer 2D physics.
- Three.js, Rapier, and Cannon-es for 3D simulation.
- Vitest for unit tests.

## AI Boundary

The AI model must not draw directly. The AI only produces or helps produce instructions:

```json
{
  "simulationType": "graph",
  "equations": ["x^2 - 4x + 3"],
  "parameters": {
    "xMin": -10,
    "xMax": 10,
    "samples": 1000
  }
}
```

The deterministic engines parse, validate, simulate, and render.

## Performance Target

Primary target hardware:

- Lenovo LOQ
- RTX 3050 Mobile 6GB

Design rules:

- Keep chat lightweight.
- Lazy-load heavy graph/physics renderers.
- Pause or throttle simulations in the background.
- Keep graph/simulation artifacts separate from chat bubbles.
- Clean up renderer state when switching projects.

## Project Mode Direction

Project Mode should become an IDE-style workspace:

- Chat
- Graphs
- Simulations
- Files
- Memory
- Projects
- Scientific notebook

Each project should persist:

- Conversations
- Files
- Graph artifacts
- Simulation artifacts
- Notes
- AI outputs

The current desktop implementation adds the first artifact and Lab workspace pieces needed for that direction.

## Project Mode Bridge

The desktop Project Mode now treats project prompts as file work, not copy-paste advice:

- The model is asked for a strict JSON manifest with complete file contents.
- If the model responds with filename-labeled markdown code blocks, MORICE converts those blocks into real files.
- If both model routes fail, MORICE uses a deterministic local fallback builder for web apps or Python starters.
- Retry phrases such as `try again` reuse the last real project request instead of becoming the new project spec.
- Every write stays inside the selected work folder and the right-side panel shows green/red diffs.
