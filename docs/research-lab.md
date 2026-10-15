# Phase 6 Research Lab

Research uses the existing chat, CapabilityKernel, TaskGraph, AgentCoordinator,
nine worker roles, permission policies, resource leases, verification contracts,
Project Builder and Device Mesh. `RuntimeServices.research` lazily composes these
objects. Research records use additive tables in the existing knowledge database.
There is no second research agent runtime, permission manager or device router.

Attach evidence and ask a research question in normal chat. The Research button
opens a compact persistent project panel. It shows provenance, stale records,
timeline, actual experiment progress and a sortable/filterable run matrix. Select
two experiments to compare their inputs, outputs, uncertainty and failures.
Parameter edits prepare a new plan; Run/Resume explicitly starts it. Stored
particle trajectories support play/pause, step, scrub, speed and trails. Displaying
a trajectory never reruns its model.

## Actual tools and contracts

| Capability | Executed tool | Scope |
| --- | --- | --- |
| research.calculate | Pint, bounded arithmetic AST | Quantities, conversion and at most 1,000 calculation sweep values |
| research.symbolic | SymPy built from a bounded AST | Dimensionless polynomials through degree eight; solve through degree two |
| research.statistics | NumPy | Descriptive, seeded bootstrap mean interval, paired/unpaired permutation, permutation ANOVA, regression and correlation |
| research.simulate | Four actual Python models | Damped steady-state oscillator, linear free thermal expansion, ideal volume-additive mixture density, classical constant-acceleration vacuum particle |
| research.trajectory | Analytic/Euler particle trajectory | 2–4,096 steps, actual positions, energy and endpoint error |
| research.material | Linear thermal mismatch | Differential expansion divided by the user's positive allowable mismatch |
| research.model_compare | Actual residual calculations | Aligned same-unit RMSE, MAE and R² where defined |
| research.cad | Parametric binary STL and JSON BOM | Rectangular solid, named dimensions, quantity, optional supplied density |
| research.ingest | Bounded file parsers | Actual selected file and stored blob hash verification |
| research.verify | Existing project integrity checks | Source bytes, relationships and freshness; no peer-review claim |

NumPy, SymPy, Pint, pypdf, openpyxl and Pillow were available in the validation
environment. SciPy, Matplotlib and CadQuery were absent and were not installed.
Their names are not reported as integrated simulation capabilities. No local
model download or GPU computation is needed for the controlled workflows.

`ResearchRuntime.execute()` returns existing typed execution/verification results.
`run_recorded()` stores the actual proof, inputs, outputs, provenance, node origin,
receipt time and time-alignment limitation. `parallel()` constructs an ordinary
TaskGraph for independent tools using the existing roles. Short arithmetic goes
directly through the Kernel and does not start agent drivers.

## Compile and execute an experiment

Use an inspectable JSON specification in chat or the panel:

````text
Study ideal mixture density:
```experiment
{
  "title": "Ideal density versus mass fraction",
  "objective": "Compare the specified ideal volume-additive density model",
  "simulation_engine": "ideal_mixture_density",
  "parameters": {
    "density_a": {"value": 1000, "unit": "kg/m^3"},
    "density_b": {"value": 2000, "unit": "kg/m^3"},
    "fraction_a": {"value": 0.5, "unit": ""}
  },
  "experiment_type": "PARAMETER_SWEEP",
  "parameter_ranges": {
    "fraction_a": {"min": 0, "max": 1, "unit": "", "points": 101}
  },
  "seed": 42
}
```
````

The compiler validates required quantities, output metrics, ranges, constraints,
seed, baseline, disk estimate and a maximum 10,000 runs. Supported types are
single run, grid sweep, Monte Carlo, optimization and one-at-a-time sensitivity.
Grid, uniform random and one-dimensional coarse/refine search are implemented.
Coarse/refine tests the first grid and then refines around its best feasible
candidate; it does not certify a global optimum. Pareto analysis compares actual
rows with explicit minimize/maximize objectives, up to 2,000 candidates.

Conservative natural-language templates reuse a saved physical specification.
For example, after supplying oscillator inputs, `Test this from 20 to 120 Hz`
compiles and runs 101 frequency cases. Missing mass, stiffness or material
properties produce a request for details in the result. Arbitrary prose is not
silently converted into a validated model. No material properties are invented
from material names.

The laboratory's one dispatch thread manages a bounded 16-job queue and SQLite
checkpoints. It submits 25-task batches through the existing coordinator and
Simulation Worker. These cheap built-in models use that coordinator's sequential
option, preserving a CPU lease for interactive work on multicore hosts. The
actual scientific tasks do not run in another worker pool. Resource admission
waits remain in the existing scheduler, outside agent workers. There are no new
long resource waits.

Pause/cancel propagates the existing cancellation token. Completed results from
the current batch are committed before stopping. Resume skips the actual saved
indices and reconstructs the seeded plan, including refined stages. A model,
compiler, quantity-normalizer, Python or Pint version change refuses resume.
Stale dependencies also require a new prepared version. Each slice is bounded
to at most 300 seconds. A crashed application requires explicit resume.

## Evidence, hypotheses and uncertainty

Projects contain structured questions, hypotheses and status, assumptions,
parameters, constraints, sources, measurements, calculations, experiments,
failures, designs, artifacts, relationships and a durable timeline. Related
chats point to the same project. Results and evidence are immutable; revised
inputs retain their previous values and invalidate transitive dependents,
including tested hypotheses and exported artifacts.

Provenance distinguishes CITED, USER_DATA, MEASURED, CALCULATED, SIMULATED,
INFERRED, ESTIMATED, HYPOTHESIS and UNKNOWN. Model text stays unverified INFERRED.
`evaluate_hypothesis()` binds a numeric threshold to a named field of actual
stored evidence and rejects invented values, nonfinite bounds and stale inputs.
It stores the evidence IDs, criterion, scope and uncertainty. A failed threshold
is a recorded contradiction. A computed outcome must have a successful stored
tool proof; source agreement does not replace that proof.

`LiteratureEvidence.cite()` requires an excerpt that occurs in current parsed
source bytes. It preserves source hash, region, DOI/URL, metadata and retrieval
time. Claim semantics and supplied bibliographic metadata still need review.
Comparison requires reviewed endpoints and explicit matching conditions. Missing
or different conditions are non-comparable; conflicting directions remain
contradictory. Equal hashes/DOIs are one study/version, not independent votes.
Corrections can be linked explicitly; automatic CrossMark/retraction monitoring
is not implemented.

`retrieve_page()` uses existing `browser.navigate` and `browser.extract`, their
permission handling and VerifiedActionRuntime. It stores actual loaded DOM text,
not search snippets. The Phase 3 browser bounds text to 16,000 characters and
handles supported embedded browser pages. Login/CAPTCHA and unavailable browser
providers remain explicit failures or user intervention.

Inferential statistics require an explicit independence/design review, reject
missing/nonfinite values and preserve method, seed and assumptions. Bootstrap
uses NumPy PCG64 and 99–2,048 resamples. Monte Carlo uses seeded Python MT19937
with supplied independent uniform distributions. Its output percentiles describe
simulation variation, not confidence intervals. No automatic sampling-bias,
normality, causal or clinical validity claim is made. Linear calibration uses
separate held-out x identifiers; repeated covariates need a more capable
sample-ID adapter. Convergence compares actual successive refinement values;
it does not validate physics.

## Files and exports

Actually tested inputs include CSV, TSV, XLSX, PDF, DOCX, JSON, XML, notebooks,
UTF-8 code/text and nucleotide FASTA, plus generated PNG images. Original bytes
are hash-deduplicated within a project. Changed selected file bytes invalidate
the previous evidence and its dependents. Imported documents, notebook cells,
source code, macros and web text never execute as instructions.

Each file is limited to 25 MiB, tables to 100,000 rows and 256 columns, Office
archives to 100 MiB expanded data, PDFs to 300 pages and extracted text to
200,000 characters. Up to 20 files can be attached per request. XLSX inspects
at most 20 sheets and keeps formula cells as text. PDF text, heuristic headings,
DOI candidates and figure-caption candidates are extracted; OCR, reliable table
layout/equation extraction and semantic figure interpretation are unavailable.
Image observations contain real thumbnail pixel statistics and links to project
hypotheses/designs/experiments, with uncertainty; no semantic scene or medical
image diagnosis is claimed. FASTA support counts bounded nucleotide records,
length and GC; it does not generate sequences, align or predict pathogenicity.
Parsers cooperate with cancellation but are not isolated hard-memory sandboxes.

Exports contain the full JSON project manifest, relative package index, copied
evidence, actual statistics CSV/SVG, experiment manifests/results CSV/plots,
verified STL/BOM, calculations, Markdown report, notebook, reproduction script
and SHA-256 manifest. Source and generated hashes are checked again. The basic
PDF summary is reopened with pypdf; it uses ASCII text, caps at 3,000 lines and
keeps complete Unicode content in Markdown/JSON. Large record snippets in the
Markdown report are explicitly marked as excerpts. The notebook is valid JSON,
with unexecuted cells; only the controlled reproduction script was executed.

Install the recorded MORICE/Python/research dependencies before running
`reproduce.py`. It recomputes scalar/calculation sweeps and exported model rows,
checks model fingerprints and compares actual numeric results. Relative paths
in `package_index.json` locate exported sources/designs after moving a package.
Historical original paths in the full manifest are retained as provenance.
Statistics/trajectories/CAD have saved inputs and proofs; their independent
rerun is not yet automated by the generated script.

## Existing Builder and Mesh integrations

`build_utility()` forwards a reviewed source proposal, requirements and runtime
check to the existing ProjectBuildRuntime. Its existing file/terminal approvals,
build, tests, execution, verification and artifact packaging remain authoritative.
The actual controlled CSV-mean utility was built, tested, executed to `2.0` and
archived by that builder. No second code generator or automatic public action
was added.

`expose_compute()` can explicitly expose the bounded read-only simulation on an
existing mesh node; its owner still must pair, trust and grant that capability.
The test executes a particle model through actual mutually authenticated TLS
between existing local mesh nodes and stores the originating device ID. It does
not certify physical Android/Linux research hardware, remote clock alignment,
hardware sensors or wet-lab measurements. Existing file receive/send can supply
research evidence; import remains an explicitly selected/authorized file action.

## Safety and practical limits

Beneficial public-data and biostatistical work is supported. The controlled
biomedical demo uses explicitly synthetic blood-pressure response values;
neither the simulation nor the statistical result is a treatment recommendation.
Harmful biological optimization and operational hazardous chemistry prompts
are rejected before project creation. The intent filter is conservative and is
not a proof of semantic classification of every sentence. The available models
also have no synthesis, wet-lab, hazardous apparatus or arbitrary execution path.

Material results model only supplied free thermal expansion or ideal density;
no general compatibility percentage, corrosion, reaction, strength or safety
certification is returned. Particle models have no material target, collisions,
penetration, radiation or relativity. Fully coupled multiphysics, CFD/FEA/SPICE,
advanced CAD/STEP, clinical validation, microscopy and autonomous literature
consensus remain unavailable. Unsupported tools fail visibly.

Repeated prepared variants and measured/model residuals support iterative work;
automatic closed-loop calibration/search across heterogeneous solvers is not
implemented. There is no result-cache claim: resume reuses saved run indices,
not unverified responses. Very long project histories need future pagination
and agent-history retention work. One-core hosts cannot promise a spare CPU
lease; honest resource-unavailable results remain possible. No GPU/VRAM use or
speedup is claimed from a resource descriptor alone.

See [the 92-item completion report](research-lab-report.md) and the separate
[final audit](research-lab-audit.md) for execution evidence and measured limits.
