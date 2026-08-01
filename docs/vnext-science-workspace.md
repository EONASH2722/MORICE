# VNext Rendering Architecture

VNext is MORICE's host-rendered artifact pipeline. Visuals appear in Normal Chat; Project Mode remains a file-building workspace.

## Contract

```text
User request
  -> visualization decision
  -> renderer selection
  -> typed data preparation
  -> queued resource work
  -> artifact validation
  -> interactive widget creation
  -> mount inside chat
  -> artifact-grounded completion
```

If any stage fails, the progress card becomes **Visualization unavailable** and MORICE states that nothing was rendered. Model prose cannot mark a job successful.

## Host Services

- **VisualizationManager:** request lifecycle, sanitization, queueing, validation, completion, and shutdown.
- **RendererRegistry:** stable renderer IDs and deterministic implementations.
- **RenderScheduler:** bounded asynchronous jobs and active-future tracking.
- **ResourceManager:** artifact cache and memory cleanup.
- **Runtime profiler:** current renderer, timing, active jobs, and resource telemetry.
- **Inline workspaces:** graph, physics, molecule, biology, data structure, chart, diagram, scene, and document widgets.

## Implemented Renderer IDs

| ID | Output |
| --- | --- |
| `math.graph` | Interactive graphs, special curves, Mandelbrot, and sampled surfaces |
| `physics.simulation` | Deterministic supported physics scenes |
| `chemistry.molecule` | Curated molecular structures |
| `diagram.structured` | Structured technical/domain diagrams |
| `biology.educational` | DNA, neuron, and cell educational models |
| `computer-science.data-structures` | Interactive data-structure operations |
| `data.chart` | Numeric bar, line, pie, scatter, and histogram charts |
| `model.schematic-3d` | Educational 2D/3D component schematics |
| `viewer.document` | Validated local file previews |

Explicit visual requests outside these deterministic builders resolve to an honest unavailable result.

## Accuracy Rules

- Mathematical expressions use an allowlisted grammar and finite sampled values.
- Graph landmarks come from the same artifact displayed by the canvas.
- Requested particle counts, projectile speed/angle, bounds, mass, and other supported parameters are parsed into host-owned simulation state.
- Physics bodies must have finite coordinates, positive mass, and positive radius.
- Chemistry structures must come from the curated library and pass atom/bond topology validation.
- Biology geometry requires finite points and real labels.
- Data structures require declared structures and initial values; operations mutate the widget's actual state.
- Charts require explicit finite numeric points.
- Schematics accept only validated primitives and label themselves educational rather than CAD-certified.
- Document preview requires an existing unchanged local file no larger than 32 MB.

Where both 2D and 3D views exist, they share the same validated artifact or simulation state; switching projection must not silently rebuild different data.

## Interaction And Export

Controls are renderer-specific and include zoom, pan, rotate, hover inspection, projection switch, pause/resume, step, replay, reset, time scale, vectors, trails, labels, and parameter editing. Export formats are enabled only where the active workspace implements them; graph and supported scene paths expose image/vector/PDF options, while physics can export state JSON.

## Performance

Rendering is lazy, jobs are bounded, hidden physics canvases stop consuming frames, background work is throttled, and resources are released on workspace close/shutdown. Frame rate depends on hardware and artifact size; 60 FPS is a target for ordinary scenes, not a guarantee for every particle count or CPU-only system.

## Limits

VNext is not a general CAD, CFD, medical, quantum-chemistry, orbital ephemeris, or molecular-dynamics solver. Curated educational models do not carry laboratory or manufacturing certification. Unknown chemistry, unsupported physics, ambiguous numeric data, and nonexistent local files fail visibly.

## Adding A Renderer

Add a stable ID, strict prompt predicate, typed builder, validator, memory estimate, and real inline widget. Tests must cover positive routing, negative routing, numerical/topological accuracy, progress-card replacement, interaction, export where applicable, hidden/closed cleanup, and failure honesty.
