# Research Core audit — 2026-10-01

Initial classification: **C — PARTIALLY IMPLEMENTED**. Existing scientific
visualization and general agents are useful foundations, not proof of an
integrated research workflow. This is a source/execution audit, not a claim
that every requested research domain has been delivered.

## Before implementation

| Feature | Evidence inspected | Initial status / action |
| --- | --- | --- |
| ResearchProject | No implementation found by symbol/source search | Missing; build persistent records |
| Storage | `autonomous_platform.KnowledgeGraphStore`, SQLite nodes/edges | Reuse same database with additive research tables |
| Tool execution | `agent_tools.ToolRegistry`, executor and cancellation | Preserve execution boundaries; add bounded deterministic research tools |
| Providers | `llm_client` GGUF/Ollama; `ModelRouter` name-based ranking | Reuse selected model through an explicit capability adapter |
| Provenance | No research claim/source association | Build evidence records, hashes and provenance validation |
| Ingestion | `MoriceWindow.on_attach` image-only picker | Extend to multiple research files; preserve image chat |
| Dataset quality | No tabular research pipeline | Build schema/missing/duplicate/outlier checks and descriptive statistics |
| Units | Scientific visuals do not provide general dimensional verification | Add bounded expression evaluator with dimensional quantities |
| Dependencies | Generic graph exists; research invalidation absent | Build transitive stale propagation |
| Artifacts | Existing renderer exports; no reproducibility package | Add parsed JSON/CSV/SVG/Markdown project package |
| History | Workspace recent chat summaries, recovery and graph conversations | Preserve; dedicated retention/archive UI remains a separate gap |
| CAD / FEA / SPICE | No verified solver installation | Report unavailable; do not manufacture solver results |
| UI | Existing background chat worker and cancellation token | Route research from ordinary chat without a new mode |

## Validation and remaining scope

## Implemented foundation — 2026-10-02

The original development brief and the later audit/rework brief are separate
documents. This work implements a bounded foundation from both. Overall status
remains **C — partially implemented**, not a completed universal research system.

| Area | Implemented evidence | Remaining boundary |
| --- | --- | --- |
| Persistent project | `research/store.py`, additive SQLite schema, source hashes, timeline and per-chat links | No full visual hypothesis/parameter editor |
| File pipeline | `research/ingestion.py`, actual PDF/DOCX/tabular parsers, bounded inputs | No OCR, research-image reasoning, video or CAD interpretation |
| Deterministic tools | `research/tools.py`, real Pint quantities, AST arithmetic and sweeps | Explicit structured inputs; no general solver orchestration |
| Model adapter | `research/providers.py`, existing GGUF/Ollama streaming with cancellation | Local adapter only; provider text remains unverified; live quality not benchmarked |
| Dependencies | Revisions mark transitive dependent records stale; cross-project links rejected | Caller must supply dependencies; no automatic recomputation |
| Exports | Sources, JSON, descriptive CSV, sampled SVG and Markdown, checksums and reparse | No PDF/notebook/CAD report generation or package import |
| History | Indexed names, compressed checked transcripts, reopen/archive/protect/retention UI | No global retention control, crash-session expiry guarantee or >10k search pagination |
| Chat integration | Existing worker pool and cancellation, multiple attachments, explicit new/resume project | Research generation occupies the ordinary generation slot; independent experiment queue is future lab work |

### Executed checks

- Focused research + workspace UI run: **52 passed in 80.88 s**.
- Full working-tree Python suite: **526 passed, 59 subtests passed in 150.00 s**.
- Website TypeScript + Vite production build: passed; Vite reported **2.98 s**.
- Real fixture PDF text extraction, CSV profiling, XLSX cells and image metadata
  were exercised together with export/reopen and checksum verification.
- Calculated kinetic energy was 9 J; a three-value speed sweep produced 1, 4, 9 J.
- Tests cover invalid units/executable expressions, unsupported files, cancellation,
  archive corruption, stale dependencies, project switching and backend errors.
- Model routing tests use explicit test providers; they are **not** remote-provider
  or real-model scientific-quality validation.
- In-app browser automation could not be invoked because its JavaScript execution
  tool was not exposed. Website build success is not visual browser QA.
- Source publication excludes separate model-provider/GPU-runtime work and existing
  screenshot deletions. An isolated staged-source test is used before publication.
- The first isolated-source suite exposed an existing timing-sensitive terminal
  cancellation test (its worker exceeded the 4-second join while packaging was
  active): 523 tests and 59 subtests passed, one failed. The exact failing test
  passed on immediate rerun in 0.52 s; this remains a known load-sensitive check.
- A second full isolated staged-source run passed: **524 tests and 59 subtests in
  101.46 s**. Its count differs from the working tree because unrelated model-runtime
  changes and their additional tests are intentionally excluded from this commit.
- PyInstaller completed the local portable rebuild. An isolated, offscreen
  startup smoke stayed running for eight seconds with no stderr, then was stopped
  by the test. This is not a visual interaction test or live-model test. The local
  package was built from the working tree, including concurrent local runtime
  edits, and is not asserted byte-for-byte equivalent to the published source.

### Completion boundary

Scientific truth is not established by file hashes or passing software tests.
There is no claimed live literature-retrieval validation, external scientific
solver integration, uncertainty propagation, formal hypothesis test suite,
automatic experiment planning, or independent biomedical/scientific review.
The attached Virtual Research Laboratory specification is a subsequent workstream,
not something this research-core audit claims to have implemented.

See [Research core usage and limits](research-core.md) for reproducible user steps.
