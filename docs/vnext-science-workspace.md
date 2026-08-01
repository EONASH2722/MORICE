# VNext Rendering Architecture

VNext renders deterministic artifacts in Normal Chat. Project Mode is a development
workspace and is not required for science visualization.

## Contract

```text
user request
  -> visualization decision
  -> renderer selection
  -> typed data preparation
  -> resource load
  -> artifact validation
  -> workspace creation
  -> mount in chat
  -> success response
```

If any stage fails, the progress card becomes an error card and MORICE states that nothing
was rendered. Model text that pretends a graph or simulation appeared is removed.

## Runtime Services

- `VisualizationManager`: owns decisions, sanitization, and lifecycle.
- `RendererRegistry`: maps stable renderer IDs to deterministic renderer implementations.
- `RenderScheduler`: bounds asynchronous jobs and tracks active futures.
- `ResourceManager`: caches reusable resources and releases them on shutdown.
- `VisualizationResult`: carries status, renderer ID, validated artifact, timing, stages, and error.
- Inline workspaces: graph, physics, molecule, biology, data structure, chart, diagram, scene, and document widgets.

## Accuracy Rules

- Equations are parsed through an allowlisted expression grammar.
- Graph landmarks are computed from the same series displayed by the canvas.
- 2D and 3D views share one validated data set or physical state.
- Physics integrators update host-owned state; the model cannot draw trajectories.
- Chemistry uses explicit atom, bond, geometry, and reference-angle data.
- A renderer must reject a request it cannot parse instead of guessing a plausible-looking result.
- Completion text is created from the exact artifact passed to that job, preventing cross-request summaries.

## Implemented Renderer IDs

| ID | Output |
| --- | --- |
| `math.graph` | 2D functions, special curves, Mandelbrot, and 2D/3D surfaces |
| `physics.simulation` | Supported deterministic physics scenes |
| `chemistry.molecule` | Curated molecular structures |
| `biology.interactive` | DNA, neuron, and cell artifacts |
| `computer-science.structure` | Interactive data structures |
| `chart.numeric` | Numeric charts |
| `diagram.structured` | Structured technical diagrams |
| `scene.component` | Educational 2D/3D component schematics |
| `viewer.document` | Valid local document previews |
| `unsupported.visual` | Honest unavailable result for explicit but unsupported visual requests |

## Interaction

Available controls depend on the artifact: zoom, pan, rotate, hover inspection, 2D/3D
selection, pause/resume, step, reset, time scale, vectors, trails, object labels, parameters,
and PNG/SVG/PDF/JSON export.

## Current Limits

VNext is not a general CAD, CFD, quantum-chemistry, medical-diagnostic, or molecular-dynamics
solver. Component schematics are educational and not dimensionally certified. Unsupported
fluids, arbitrary molecules, or ambiguous prompts fail visibly. Performance depends on artifact
size and the host GPU; background work is bounded so chat remains responsive.

## Extending VNext

Add a renderer with a stable ID, strict request predicate, typed artifact builder, validator,
and inline workspace. Add positive, negative, and cross-routing tests before registering it.
Never add a prose-only placeholder for an unimplemented renderer.
