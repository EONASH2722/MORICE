# MORICE VNext Rendering Architecture

VNext is MORICE's validated visualization runtime. It renders supported
artifacts inside Normal Chat and rejects unsupported requests honestly. Project
Mode remains a file-building workspace.

## Runtime Pipeline

```text
Normal Chat prompt
  -> deterministic intent decision
  -> renderer registry selection
  -> bounded background render queue
  -> typed data preparation
  -> numeric and structural validation
  -> real interactive chat workspace
  -> optional Lab archive
```

The model can suggest intent, equations, and parameters. It is never treated as
proof that a visualization exists. A success card appears only after a renderer
returns a validated artifact.

## Implemented Renderers

| Renderer | Real output | Interaction | Validation |
| --- | --- | --- | --- |
| Function graphs | Cartesian, multiple equations, piecewise, polar, parametric, and implicit curves | Pan, zoom, hover coordinates, reset, large view, PNG/SVG/PDF | Safe expression AST, finite samples, numeric roots, extrema, intercepts, and inflection checks |
| Surface graphs | Sampled `z=f(x,y)` mesh and matching 2D height map | 2D/3D switch, rotate, zoom, hover, PNG/SVG/PDF | Safe two-variable AST, finite grid, exact sampled min/max |
| Physics | Particles, projectile, pendulum, spring, wave, circular motion, and orbit | Pause, resume, step, step back, reset, speed, gravity, trails, vectors, 2D/3D projection where supported, PNG/JSON | Deterministic initial state, bounded values, mass-aware collisions, finite state |
| Molecules | Curated VSEPR structures | 2D/3D switch, rotate, zoom, atom inspection, PNG/SVG/PDF | Known topology, validated atom/bond indices, reference-angle coordinate models |
| Biology | DNA, neuron, and cell geometry | 2D/3D switch, rotate, zoom, pause, labels, PNG | Finite geometry, valid connections, deterministic layout |
| Data structures | BST, AVL, graph, linked list, queue, stack, and hash table | Insert, delete, search, animated highlights, complexity display | Deterministic state and structure-specific operation rules |
| Numeric charts | Bar, pie, line, scatter, and histogram from prompt-supplied values | Exact-value hover, large view, PNG/SVG/PDF | At least two finite labeled points; no invented values |
| Component schematics | Curated robot, drone, vehicle, aircraft, ship, building, bridge, engine, CPU, GPU, motherboard, camera, and watch assemblies | 2D/3D switch, rotate, zoom, pause, component inspection, PNG | Positive finite primitive geometry and valid component links |
| Diagrams | Networking, OS, database, AI, security, biology, circuits, geography, economics, compiler, timelines, and explicit user-supplied flows | Pan, zoom, node inspection, PNG/SVG/PDF | Known or user-supplied nodes, valid edge endpoints, deterministic layout |
| Local documents | Text, source, JSON, CSV, images, and PDF from an explicit local path | Native in-chat preview and open-in-default-app action | Existing file, stable size, supported extension, 32 MB pipeline limit |
| Rich answers | Markdown, code highlighting, tables, and KaTeX math | Selection and copying inside the answer view | Local bundled assets; no network dependency |

The 2D and 3D controls are projections of one validated artifact. Switching
views does not ask the model to regenerate values.

## Accuracy Contract

- Equations are parsed by a restricted numeric expression evaluator.
- Graph landmarks are calculated from the sampled function and refined
  numerically instead of guessed from model prose.
- Surface legends report the actual sampled extrema.
- Particle simulations use deterministic state and fixed-step integration.
- Molecule coordinates reproduce a reference angle where a single constrained
  VSEPR geometry permits it. More highly distorted molecules are labeled
  `idealized-vsepr`; measured/reference angles remain separate from the
  schematic coordinates.
- Unsupported SPH fluids, soft bodies, rigid-body constraint systems, arbitrary
  molecules, and arbitrary non-curated 3D objects return a capability error.
  Local document viewing requires a valid path to a supported file. MORICE
  never substitutes an unrelated animation, guessed data, or invented geometry.

These are interactive educational and engineering visualizations, not a
certified CFD, quantum chemistry, or finite-element solver.

## Runtime Ownership

- `morice/visualization.py`: registry, capabilities, scheduler, cache,
  validation boundary, progress stages, error recovery, and fake-output guard.
- `morice/science_engine.py`: graph/surface generation and deterministic physics
  instructions.
- `morice/domain_engine.py`: curated chemistry and structured-diagram artifacts.
- `morice/educational_engine.py`: biology and interactive data-structure artifacts.
- `morice/universal_engine.py`: numeric charts, local documents, and curated
  2D/3D component schematics.
- `morice/pyside_app.py`: in-chat workspaces, rendering, controls, exports,
  resource cleanup, and Project Mode IDE panel.
- `vnext/`: strict TypeScript contracts, coordinator, renderer manager, Plotly
  adapter, cache, and deterministic 2D/3D particle-state engine.

## Project Mode

Project Mode is intentionally separate from VNext science rendering:

- File tree and source preview.
- Green/red unified diffs.
- Build output and a direct-command allowlisted terminal.
- Safe path checks and staged source writes.
- Source validation before replacement.
- Run and verify actions with detected entry points.
- Folder-only or full-access policy displayed in the composer.
- Local or online-plus-local project context.

The model is asked for a strict file manifest. MORICE converts the manifest into
editable files, validates paths and source, stages writes next to each target,
then replaces files. If model output is unusable, the local fallback builder
creates a real starter project rather than returning copy-paste instructions.

## Performance

- Heavy artifact generation runs on a bounded worker pool.
- Artifacts use an LRU-style memory budget.
- Hidden simulations stop consuming timer frames.
- Physics uses fixed time steps and spatial collision partitioning in the
  desktop engine.
- 3D is projected from real depth state; unsupported GPU backends are reported
  unavailable instead of claimed.
- Web assets are bundled and lazy-loaded locally.

Primary QA target: Windows 10/11 and the Lenovo LOQ class of hardware, including
RTX 3050 Mobile 6 GB systems.

## Verification

Python tests cover graph landmarks, discontinuities, repeated roots, implicit
contours, piecewise functions, surfaces, physics configuration, replay, 2D/3D
state, molecular angles, biology geometry, data-structure operations, chart
value preservation, all curated schematic families, the extended domain
diagram matrix, local file previews, inline widget replacement, exports, honest
failures, Project Mode safety, desktop identity, and long-answer continuation.

`tests/test_rendering_accuracy_matrix.py` adds a representative ten-case
contract across Cartesian, implicit, polar, parametric, and surface graphs;
projectile, pendulum, and 3D particle physics; VSEPR chemistry; and directed
network diagrams. Each case validates numeric or structural truth rather than
only checking that an artifact object exists.

The TypeScript suite covers prompt coordination, piecewise parsing,
capability selection, artifact caching, fail-closed behavior, deterministic
particle state, bounds, and real 3D depth.

Before publishing a build:

```powershell
python -m unittest discover -s tests -v
cd vnext
pnpm typecheck
pnpm test
```

## Extension Rule

A future renderer must implement:

1. A unique capability ID.
2. Prompt matching that does not steal unrelated requests.
3. Typed artifact construction.
4. Validation independent of model prose.
5. Memory estimation and cleanup.
6. An honest unsupported or failed state.
7. Automated numeric and visual QA.

No renderer may claim success from placeholder text.
