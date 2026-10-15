# MORICE Phase 6 — Research Lab completion report

Validation date: 2026-10-04. Actual checkout: `E:\MORICE`. This report covers the
executed bounded research workflows and identifies unavailable domains explicitly.
No commit, push, release, binary upload, deployment or public-site change was made.
**Phase 6 is complete for the available controlled workflows, with the concrete
technical limitations listed below.** Final regression: 811 tests and 59 subtests
pass. Startup, local packaging, actual execution and separate audit also pass.

1. **Phase 1 status.** The existing CapabilityKernel, registry, TaskGraph,
   typed results, permissions, risk handling, resource leases, events, timeout and
   telemetry contracts remain the execution authority. Fresh prerequisite tests
   and the full suite exercise them; research registers ten additional capabilities.

2. **Phase 2 status.** Existing AgentCoordinator, WorkerManager, nine roles,
   SharedTaskState, model budget and scheduler remain in use. Research extends
   researcher/analyst/verifier/simulation capabilities. Simple calculations stay
   on the direct Kernel path. No duplicate agent runtime was introduced.

3. **Phase 3 status.** Existing VerifiedActionRuntime, action bindings, browser
   DOM observations, verification, recovery and journal remain authoritative.
   Actual research-page navigation/extraction and citation anchoring pass in a
   real Qt browser. General desktop semantic vision remains constrained below.

4. **Phase 4 status.** Research forwards source, requirements and explicit
   authorization to ProjectBuildRuntime. A real CSV-mean Python utility was
   built, tested, run to `2.0` and archived through that builder.

5. **Phase 5 status.** Existing pairing, mutual TLS, capability grants, node
   registry, leases, remote verification and file transfer remain intact. A real
   particle-model RPC between existing local mesh nodes produces x = 6 m and
   retains device origin. Android/Linux physical research hardware is unverified.

6. **Prerequisite repairs.** Initial fresh checks found a PID-fixture publication
   race, repaired with an atomic temporary-file rename without weakening process
   reaping assertions. Fresh prerequisite rerun: 224 passed in 130.55 s. A later
   full run exposed document preview precedence when paths contained biology
   keywords; explicit document requests now take precedence, with a deterministic
   regression. The load audit also repaired CPU starvation by selecting existing
   serial agent execution for the cheap model batches.

7. **Research Lab architecture.** Lazy ResearchRuntime composition, existing
   Kernel execution, existing TaskGraph/agents for batches, additive research/lab
   SQLite tables and owned artifacts. One bounded job-dispatch thread manages
   checkpoints; it is not another scientific worker pool. The UI preparation
   helper compiles plans; actual calculations use existing execution authorities.

8. **ResearchProject model.** A persistent structured view over ResearchStore
   includes ID, objective, timestamps, typed records, relationships, timeline and
   related chats. Restart loads the same project and run records outside chat.

9. **Research question model.** Explicit question text, domain, importance,
   status, answer state and uncertainty are stored when a runtime project is
   created. Questions remain open until reviewed; no model prose closes them.

10. **Hypothesis model.** Existing explicit hypothesis states and revisions are
    retained. Threshold tests require current evidence, finite criteria, matching
    provenance and the actual stored numeric outcome; forged values are rejected.

11. **Assumption tracking.** Assumption records retain previous and next values,
    scope, provenance and timeline. Experiments/calculations/designs can explicitly
    depend on them; inferred assumptions do not become measured properties.

12. **Dependency invalidation.** Changed parameters/assumptions and replaced
    selected source bytes invalidate transitive calculations, designs, runs,
    tested hypotheses and artifacts. Model/compiler/normalizer/Python/Pint
    fingerprint changes refuse resume. The actual demo marks 13 records stale.

13. **Knowledge graph.** Existing additive research edges express depends_on,
    derived_from, supported_by, tested_by, contradicted_by and other supported
    relations. Cross-project dependencies and dangling relationships are checked.

14. **Timeline.** Project creation, record insertion, input revision, dependency
    invalidation and relationships are persisted. The panel can inspect the last
    50 timeline events; the full manifest preserves the complete project history.

15. **Provenance system.** CITED, USER_DATA, MEASURED, CALCULATED, SIMULATED,
    INFERRED, ESTIMATED, HYPOTHESIS and UNKNOWN remain distinct. Tool inputs,
    methods, actual results and verification proofs accompany recorded execution.

16. **Evidence model.** Immutable source bytes, hashes, parsed regions, reviewed
    citations, observations, tool proofs and model limits accompany claims.
    Models provide unverified interpretation, not numeric or citation proof.

17. **Ingestion pipeline.** Selected files pass existing file-read policy and
    the existing secret-path guard. Parsed output, source and stored bytes are
    hash-verified. Changed inputs preserve old evidence as stale. Imported code,
    notebook cells, macros and document instructions never execute.

18. **Supported file formats actually tested.** CSV, TSV, XLSX, text PDF,
    DOCX, JSON, XML, notebook, UTF-8 text/code, nucleotide FASTA and PNG. STEP
    and unintegrated formats fail explicitly. Other declared image formats share
    Pillow parsing but were not separately exercised for every encoding.

19. **PDF support.** Actual six-page PLOS PDF: 38,330 extracted characters,
    references/results heading candidates and two figure-caption candidates.
    A published correction PDF was also ingested. No OCR, reliable equation/table
    reconstruction or semantic figure interpretation is claimed.

20. **Dataset support.** Actual UCI Iris bytes: 150 rows, four numeric columns
    with cm labels and a class column; three duplicate rows retained/reported.
    Mean sepal length = 5.843333333333334 cm. Actual XLSX/TSV fixtures also pass.

21. **Image support.** Actual PNG metadata and sampled thumbnail pixels are
    inspected; image observations link to current hypotheses/experiments/designs.
    Contextual interpretation remains uncertain. No scientific object recognition,
    microscopy analysis, diagnostic or semantic scene proof is claimed.

22. **Multi-file reasoning.** Paper, correction, actual CSV and a clearly
    synthetic diagram enter one project and shared bounded evidence context.
    The hypothesis test binds actual CSV-derived statistics and linked source
    IDs. The paper provides methodology context, not evidence for a clinical claim.

23. **Mathematics tool integration.** Pint executes bounded numeric expressions;
    SymPy executes constructed polynomial differentiation, integration and
    quadratic solving. Function calls/imports and arbitrary expression execution
    are rejected. No fabricated external CAS/solver result appears.

24. **Unit handling.** Pint validates dimensions and output conversions;
    incompatible requested units fail. Model parameters/ranges/constraints are
    converted to declared units. Statistical y/x unit labels are validated.
    Model-vs-data arrays must already be explicitly aligned and in matching units.

25. **Statistics support.** Actual NumPy descriptions, quantiles, sample
    standard deviation, regression/correlation, bootstrap mean interval and
    paired/unpaired/ANOVA permutations. Seeded resampling and input/design
    failures are tested. No automatic causal, normality or sampling-bias claim.

26. **Visualization.** Actual dataset statistics CSV/SVG and experiment scatter
    SVGs are written and parsed. Units/ranges/sampling labels are present. A
    trajectory panel renders actual stored positions and trails. External
    Matplotlib was unavailable; these are deterministic SVG/PySide outputs.

27. **ExperimentCompiler.** Inspectable specifications contain objective,
    tool, quantities, ranges, seed, metric/direction, constraints, baseline,
    hypothesis, priority, dependencies and time slice. Conservative NL templates
    reuse a supplied model context and report missing inputs rather than inventing them.

28. **Experiment types.** SINGLE, PARAMETER_SWEEP, MONTE_CARLO, OPTIMIZATION
    and SENSITIVITY_ANALYSIS execute. Other proposed domain-specific experiment
    types are unavailable without actual integrated models.

29. **Simulation tool registry.** Four actual local Python models with declared
    inputs, output units, method, version/fingerprint, CPU availability and limits.
    Unknown tools fail. Availability is not inferred from a product name.

30. **Tools actually available.** NumPy 2.5.2, SymPy 1.14.0, Pint 0.26.1,
    pypdf 6.19.0, openpyxl 3.1.5 and Pillow. SciPy, Matplotlib and CadQuery were
    absent. No tool/model download was performed. No research GPU adapter is integrated.

31. **Parameter sweeps.** Actual 1,001-run density grid plus a 10,000-run
    capacity test. 25-task checkpoints, persisted matrix, actual progress,
    pause/cancel/resume and all final counts are verified.

32. **Adaptive search.** One-dimensional coarse/refine optimization performs
    a coarse grid and a real refined grid around its best feasible point. Random
    bounded search is also supported. Bayesian/surrogate/general adaptive solvers
    are not integrated.

33. **Monte Carlo.** 1,000 actual draws with seed 42 and independent uniform
    input ranges. Repeated tests reproduce parameters and results. Empirical
    percentiles and constraint-violation fractions carry assumptions and limits.

34. **Sensitivity analysis.** Actual baseline plus one-at-a-time grids;
    22-run demo records output/input spans and their ratio. This is local/model
    sensitivity, not a universal global attribution method.

35. **Optimization.** The 202-run coarse/refine density experiment reaches
    the best tested feasible endpoint. Baseline comparisons and constraint
    failures are supported. The best observed candidate is not certified global optimality.

36. **Pareto analysis.** Actual dominance checks with explicit directions,
    finite rows, at most 2,000 candidates and four objectives. Tests exercise
    the real nondominated indices; no synthetic performance front is shown.

37. **Material compatibility.** Defined thermal mismatch/allowable ratio.
    Demo: 0.001 m mismatch / 0.0001 m allowance = 10, outside tolerance.
    This does not establish chemical, corrosion, strength or general compatibility.

38. **Composition sweep.** User-supplied component densities and mass
    fraction in [0,1]; ideal volume-additive density ranges from 2,000 to
    1,000 kg/m³. No reaction, phase, solubility or miscibility prediction.

39. **Particle simulation.** Safe single classical vacuum point particle,
    bounded duration and nonrelativistic speed. Endpoint positions, speed and
    kinetic energy are calculated and independently checked. No material targets.

40. **Time-dependent simulation.** Actual analytic and Euler trajectories
    contain time, x/y, speed and energy. The panel provides play/pause, step,
    scrub, speed and trails using stored rows, without rerunning calculations.

41. **Multiphysics handling.** Thermal dimensional fit is an explicit
    one-way use of supplied temperature change and expansion coefficients.
    No thermal-mechanical feedback, coupled FEA, electromagnetic/thermal system
    or fully coupled solver is integrated; requests for those do not produce scores.

42. **Convergence testing.** Actual Euler step refinements 10/20/40 give
    position errors about 0.2/0.1/0.05 m. Successive-difference testing records
    tolerance and scope. Exact analytic comparison is distinct from physical validation.

43. **Model-vs-data validation.** Actual residual arrays, RMSE, MAE and R²
    where defined. A deliberately mismatched measurement fixture produces
    nonzero residuals. Units/alignment are explicit caller responsibilities.

44. **Model calibration.** Actual NumPy linear least squares with disjoint
    held-out x identifiers, separate fit/validation counts and held-out metrics.
    Training-only validation is rejected. General sample-ID/parameter estimation
    and clinical model validation remain unavailable.

45. **Engineering integration.** Unit calculations, model comparisons,
    parametric dimensions, immutable design versions, component quantities,
    density-derived mass and actual STL/BOM artifacts. No structural or manufacturing certification.

46. **CAD.** Actual 684-byte binary STL, 12 triangles and metre coordinates.
    Reopening checks hashes, finite geometry, closed manifold edges and bounding
    dimensions. CadQuery/STEP/FEA/freeform geometry are not integrated.

47. **BOM.** Actual JSON part/quantity/material/reference/dimensions/volume;
    optional supplied density gives modeled unit mass. Hashes and dimensions are
    reopened. No invented supplier, price, material strength or sourcing claim.

48. **Project Builder integration.** Same ProjectBuildRuntime and its
    existing permissions, source proposal, command validation, test/run checks
    and archives. Verified CSV utility proof is in the research integration test.

49. **Device Mesh integration.** Same mesh/Kernel; owner explicitly exposes
    read-only research.simulate, pairs, trusts and grants. Node-origin metadata
    and receipt time are stored. Existing file transfer can supply selected inputs.

50. **Literature research.** Actual publisher paper/correction ingested,
    source excerpt/hash anchored, DOI/URL recorded and correction linked. An
    actual browser fixture demonstrates verified loaded DOM retrieval through
    Phase 3. General autonomous systematic review and bibliographic certification remain constrained.

51. **Contradictory evidence handling.** Reviewed same-metric/same-condition
    opposing source assertions remain CONTRADICTORY. Missing/different conditions
    are NON_COMPARABLE; equal hashes/DOIs are one study/version. No fabricated consensus.

52. **Biomedical research.** Beneficial data analysis and actual seeded
    bootstrap uncertainty work. The demo's ten blood-pressure responses are
    explicitly synthetic. Public methodology literature is real. No clinical
    efficacy, diagnostic or treatment claim is validated.

53. **Biological safety.** Harmful virulence/transmissibility optimization
    test prompts are rejected before project creation. Only closed computational
    adapters execute; no sequence generator, harmful biological optimizer or wet-lab path.

54. **Chemistry safety.** Operational toxic-gas preparation is rejected;
    available models do not provide synthesis, recipes, hazardous hardware or
    reactions. Intent matching is conservative, not complete semantic certification
    of arbitrary text or third-party code. Optional model interpretations remain unverified.

55. **Self-verification.** Same Kernel verification contracts: independent
    model equations, deterministic recomputation, actual file hashes, reopened
    geometry/BOM and export parsers. Scientific model assumptions and source
    semantics are not certified by an execution proof.

56. **Negative result handling.** Failed thresholds are CONTRADICTED;
    invalid/infeasible runs retain errors. Zero feasible candidates produce FAILED
    without a best candidate. Unsupported adapters never become successful simulations.

57. **Uncertainty.** Methods, bounds, sampling/design caveats, small-n
    warnings, empirical simulation variation, bootstrap interval assumptions,
    convergence scope and source conflicts persist with results. No invented compatibility percentage.

58. **Reproducibility.** Actual inputs, seed, Python/tool versions,
    model/compiler/normalizer fingerprint, complete run rows, checksums and
    controlled reproduction script. A fresh process recomputes 2,225 exported
    model rows and 9 J. Other research capabilities have saved inputs/proofs but
    are not all automated by the generated script.

59. **Artifact package.** Full project JSON, relative package index,
    original evidence, CSV/SVG, experiment manifests/results, STL/BOM, calculations,
    README, actual PDF summary, unexecuted notebook, reproduction code and hashes.
    Latest demo path is recorded in `build/phase6-benchmark.json`.

60. **Report generation.** Actual Markdown/full JSON plus an actual reopened
    PDF. Basic PDF summary is ASCII, at most 3,000 lines; full Unicode/structured
    content stays in JSON/Markdown. Large Markdown payload excerpts are labeled.

61. **Research resume.** Project records, timeline, chat links, experiments
    and SQLite run checkpoints survive restart. Resume uses stored parameters,
    versions, seed and completed indices; no silent crash restart or mixing versions.

62. **Background research.** One bounded 16-job priority queue, existing
    cancellation, real progress and owned outputs. Phase 6 does not schedule
    unattended future research or create Phase 7 event connectors.

63. **Resource scheduling.** Existing admission, leases and worker bounds
    remain. Cheap model batches use existing serial scheduling to leave CPU
    capacity for interactive work on multicore hosts. Independent heavy-capable
    tasks can use the same parallel TaskGraph API. No new blocking resource wait.

64. **Remote compute.** Actual mutually authenticated local TLS node execution,
    permission refusal coverage and node-origin proof. No research hardware
    benchmark, remote clock synchronization or GPU acceleration was validated.

65. **End-to-end calculation demo.** Explicit 2 kg and 3 m/s produce 9 J;
    incompatible metre output and injected Python expression fail. Direct arithmetic
    does not initialize the agent pool or a local model.

66. **Paper demo.** Publisher PDF is 255,629 bytes, six pages, SHA-256
    `ffc1005680cb620eec4c913437dfabbf311b535cfe16cbaeb2faec1f92afc362`.
    The 2022 correction is retained as a correction to that essay, not another study.

67. **Dataset demo.** UCI archive SHA-256
    `d11fe30213d36434a0879aab7cb00ce3c812eb7ba2495874438abff7b7b762e9`.
    The original data is preserved; a documented CSV header is added. 150 rows,
    three duplicate rows and mean sepal length 5.843333333333334 cm are measured
    from those retrieved bytes, including the source's version differences.

68. **Multimodal demo.** Real paper/correction/CSV and a labeled synthetic
    PNG share a project. Real statistics and evidence IDs test the hypothesis;
    image pixel/context records preserve their uncertain interpretation. No
    uninstalled vision model or invented visual conclusion is used.

69. **Parameter sweep demo.** 1,001-run density sweep plus 10,000 actual
    capacity-test runs; endpoint values and exported row counts verified.

70. **Monte Carlo demo.** 1,000 seed-42 uniform draws, actual constraints,
    outputs, empirical statistics and retained invalid/infeasible counts.

71. **Optimization demo.** 202 actual coarse/refined runs of the defined
    ideal density model, with best tested feasible candidate and artifact checksums.

72. **Particle demo.** Classical safe vacuum trajectories, actual energy/
    position fields and refinement errors; remote constant-velocity case reaches 6 m.

73. **Material demo.** Defined thermal mismatch ratio = 10, explicitly outside
    user-supplied tolerance; actual STL/BOM created and corruption rejection tested.

74. **Failed hypothesis demo.** The actual dataset mean is below the
    prespecified 6 cm threshold, so status is CONTRADICTED. A caller cannot
    substitute 20 for an evidence value of 2 in the adversarial test.

75. **Stale-dependency demo.** Revising the shared assumption marks 13 real
    records stale, including the tested hypothesis. Selected-source changes and
    changed model fingerprints also refuse current-result/resume claims.

76. **Safe biomedical demo.** Synthetic treatment-response uncertainty
    computed with an actual NumPy bootstrap; design limitations and no clinical
    validation remain attached. Beneficial work and harmful-intent refusal are tested.

77. **Tool failure demo.** Uninstalled CFD request returns typed failure,
    UNKNOWN/failure provenance and no simulation result. A forged density adapter
    output fails independent verification. Infeasible optimization stays failed.

78. **Project Builder research demo.** Reviewed actual CSV-mean source,
    unittest fixture and explicit command requirement run through existing
    Builder, produce stdout `2.0`, pass definition-of-done and create an archive.

79. **Device Mesh research demo.** Existing real three-node TLS test fixture;
    paired/granted second node executes a vacuum particle model. Output x = 6,
    successful remote proof and originating node ID are retained. No mock transport.

80. **Benchmark results.** Latest controlled workflow: ingest 436.64 ms;
    warm calculation median 2.925 ms; sweep 1,001 runs 1.785 s; Monte Carlo
    1,000 runs 1.652 s; optimization 202 runs 0.471 s; sensitivity 22 runs
    0.142 s; export 355.12 ms; reproduction subprocess 754.77 ms; reopen 2.485 ms.
    Capacity check: 10,000 runs in 16.981 s (~588.88/s), 547 progress samples,
    250 interactive samples. Echo median 0.156 ms; calculation median 16.271 ms,
    maximum 152.572 ms under load. These are measurements, not latency guarantees.

81. **CPU/RAM observations.** Controlled workflow: 5.5 process CPU seconds,
    RSS 48,291,840 to 100,827,136 bytes. Capacity run: 14.578 CPU seconds,
    RSS 64,675,840 to 84,271,104 bytes; isolated owned disk 2,947,164 bytes.
    Four-worker configured limit, one model worker active for cheap serial batches,
    25-task checkpoints and zero leases after shutdown. Main demo's 7,398,472
    owned disk bytes include retained earlier local evidence/demo packages.

82. **GPU/VRAM observations.** Research models use CPU. GPU use false;
    VRAM not measured. Existing GPU lease descriptors are scheduling budgets,
    not proof of discovered or accelerated research hardware. No model download.

83. **Tests added.** 34 Research Lab cases, including parameterized format/
    safety cases, and one document-intent regression. Existing 16 research-core
    compatibility cases remain. Coverage includes real tools/files/Qt/browser/
    Builder/TLS, seeds, errors, forged results, staleness, pause/cancel/resume,
    CPU admission, permissions, numerical quality and export reproduction.

84. **Targeted test results.** Fresh prerequisite suite 224 passed;
    integration/mesh/builder/agent selection 159 passed in 147.77 s before final
    audit additions. Final research/core/visualization audit selection: 101 passed
    and 35 subtests in 54.19 s. Logs are in `build/phase6-*.log`.

85. **Full regression results.** Final current-source run: **811 passed and
    59 subtests passed in 281.88 s**, `build/phase6-verified-full-tests.log`.
    Earlier 800/59 pass run and a subsequent 808/59 pass run with one
    preview-routing failure are retained. The latter failure was repaired and
    the fresh full run passed; no test was skipped or weakened to obtain that result.

86. **Startup health.** Latest real isolated services/main window/panel:
    constructor 270.48 ms, total 1,458.72 ms, no critical failures. Research,
    mesh, builder and agent drivers are lazy at startup; same Kernel/agents/actions,
    nine roles, direct echo median 0.336 ms, first verified calculation 372.52 ms.
    Calculation/panel do not start agent drivers; lab dispatch stops and leases return to zero.

87. **Packaging.** Current local source wheel: 2,020,184 bytes, 75 runtime
    modules including 20 research modules and five integration modules source-equal;
    ZIP integrity passes. SHA-256
    `6921aa6e5a418bf083778e5f34e95080657ec2f66b0f3b97b18c27ac83e5de34`.
    An isolated process actually imports from that wheel, calculates 9 m² and
    compiles an experiment with a stable model fingerprint. Final parity passes.
    Frozen executable/physical Android/Linux research validation was not performed.

88. **Performance regressions.** Explicit contention test repaired rejection
    of interactive calculation during cheap parallel batches. Direct startup echo
    remains ~0.3 ms (Phase 5 measurement ~0.316 ms). Cold research activation/
    Pint normalization adds measured latency only when research is used. Different
    startup wall times are not attributed solely to this change. No parallel speedup claim.

89. **Remaining limitations.** Bounded four-model research, conservative NL,
    sampled image pixels/context, no universal semantic vision/OCR/clinical
    certification/general materials compatibility/fully coupled multiphysics/
    external CFD/FEA/SPICE/freeform CAD. Basic ASCII PDF, partial automatic
    reproduction coverage, no general verified-result cache, no distributed
    clock calibration, no parser hard-memory sandbox and no long-history
    pagination. One-core/resource-saturated hosts cannot guarantee spare CPU.
    Independent/dependent sampling and source semantics still require review.

90. **Phase 7 readiness.** Shared capability, event, permission, result,
    provenance and project interfaces can accept externally connected inputs
    without replacing the research core. Phase 7 connectors/event automations
    were not implemented or started. Final checks pass; ready for the Phase 7 prompt.

91. **Phase 8 readiness.** Persistent goals/questions/evidence, background
    checkpoints, artifacts and typed results provide extension points. Phase 8
    requirements have not been supplied or validated; readiness is architectural.

92. **Phase 9 readiness.** Actual engineering artifacts and existing Builder
    integration can support future generators. No Phase 9 generator ecosystem,
    advanced CAD exporter or requirement-specific behavior was implemented.

## Required carry-forward: exact Phase 2 limitations

| Original limitation | Phase 6 audit outcome |
| --- | --- |
| Web mainly search snippets | Shared Phase 3 verified embedded-browser navigation/extraction executes for supported pages; research stores actual loaded DOM text. General login/CAPTCHA/arbitrary-browser support remains constrained; DOM text cap is 16,000 characters. |
| Vision mostly metadata | Real sampled image pixels and research context are added. Full semantic screen/research-image understanding is still unavailable and explicitly documented. |
| No desktop observe/recover loop | Shared VerifiedActionRuntime's bounded observe/verify/recover loop is retained and tested. Universal desktop/provider coverage remains unavailable. |
| Resource waits occupy workers | Existing scheduler admits research task leases before worker execution. No new long wait was added. Cheap serial batches address interactive CPU contention; single-core/saturated-host limits remain concrete. |
| Small tasks slower in parallel | Bounded arithmetic continues the inline Kernel path without agent drivers. Cheap model batches use the existing sequential option; independently parallel tasks still use the existing coordinator. |

## Evidence and primary references

Local evidence: `build/phase6-prerequisites.log`,
`build/phase6-final-audit-tests.log`, `build/phase6-verified-full-tests.log`,
`build/phase6-benchmark.json`, `build/phase6-limits-benchmark.json`,
`build/phase6-browser-demo.json`, `build/phase6-startup.json`,
`build/phase6-package.json`. Implementation/limits: [guide](research-lab.md).
Separate final review: [audit](research-lab-audit.md).

Public paper: [Ioannidis, PLOS Medicine, 2005](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.0020124).
Its [2022 correction](https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1004085)
addresses Table 2 and is preserved as a related version.
Dataset: [UCI Iris](https://archive.ics.uci.edu/dataset/53/iris),
[dataset DOI](https://doi.org/10.24432/C56C76); the repository documents differences
from the historical article, which the demonstration does not silently correct.
Method documentation: [NumPy generators](https://numpy.org/doc/stable/reference/random/generator.html),
[SymPy calculus](https://docs.sympy.org/latest/tutorial/calculus.html),
[Pint](https://pint.readthedocs.io/en/latest/api/base.html).
