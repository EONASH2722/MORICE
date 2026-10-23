# MORICE 0.9.5 implementation and validation report

Implementation began 2026-10-22; release verification continued 2026-10-23. This report distinguishes shipped behavior, measured local fixtures and validation limits. The upgrade has no end-of-life designation.

## Technical reply amendment (2026-10-24)

The [technical reply report](technical-replies-0.9.5.md) describes corrected written-analysis routing, installed-default Research synthesis, complete current-prompt preservation, per-request generation budgets and completion timers. A conditional electromagnetic harvester adapter now uses the existing Kernel and independent phasor/energy verification to ground complete labelled inputs. This does not certify model-generated engineering recommendations or proposed hardware. Private reproduction prompts and generated responses are excluded from public source and documentation packages. The validation table later in this document describes the initial build; the current release manifest and amendment receipts identify replacement binaries.

## Duplicate-message amendment (2026-10-23)

The reported duplicate was reproduced in the production Qt shell: a streamed reply displayed with the configured “Sir” address did not receive its raw saved message's ID. Paging forward consequently loaded the same saved answer again. Persistence now matches the presented form while preserving existing stable IDs and assigning each repeated answer its own turn identity. Partial stream rows cannot borrow an older answer's ID. Returning from older pages reuses an already rendered latest reply instead of appending it again. No retained transcript is deleted or deduplicated by text.

Regression coverage exercises streaming, forward pagination, identical replies across separate turns, persisted transcript identity, returning from older pages, and the screenshot's informal date question. The date spelling now reaches the deterministic local clock helper. Focused verification passed 22 tests and 3 subtests. The final full regression and frozen/package checks gate replacement of the existing 0.9.5 release assets and local dist application; no new release or version is created. The original validation table below describes the initial 0.9.5 build; amendment receipts identify its replacement.

## Architecture and prerequisite repairs (brief items 1–4)

The [pre-change audit](fast-memory-architecture-0.9.5.md) records the existing owners. RuntimeServices still owns AgentOrchestrator, ModelRouter, ContextManager, the Capability Kernel, background tasks, resource leases, DesktopIntegrationLayer and voice. Existing verified actions, agents, Builder, Research, Device Mesh, media and spatial tools retain their execution boundaries. No second agent runtime or model scheduler was introduced.

ChatHistory previously retained checksummed compressed transcripts in the shared knowledge SQLite database; the UI and model used recent windows. MemoryManager already provided local scoped records. The update extends both stores. AgentRequestContext and workflow ExecutionContext now carry the active conversation identity; compact worker packets accept only matching, bounded memory data and label it untrusted.

Repairs include natural-language calculator parsing and bounded exponents, immutable route selection before request creation, safe delayed callbacks after Qt widget destruction, missing-index-metadata recovery without erasing message rows, transactional preference-write rollback, context limits for auxiliary system data and serialized local generation. The reported scrolling defect required preserving viewport anchors, paging both directions and deferring streamed UI output while the reader is on older messages.

The actual application launcher selects **Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf**, 2,889,513,280 bytes, when the saved thinking model is empty. A bare backend import has a different coder-model fallback; it is not the launcher's selected thinking profile. The saved thinking selection and its sampling controls are preserved.

## Fast model and routing (items 5–22)

The user explicitly authorized downloading and testing the preferred fast model after initially choosing implementation without download. The installed artifact is **Qwen3-4B-Instruct-2507-Q4_K_M.gguf**, 2,497,281,120 bytes, Apache 2.0. Sources: [official Qwen model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) and [pinned Unsloth GGUF artifact](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf). SHA256: `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`.

The GGUF v3 metadata identifies Qwen3, 36 blocks, GPT-2 BPE tokenizer, EOS 151645, padding 151654 and its embedded chat template. The model loaded and streamed actual responses using local CUDA llama-server build 10408, commit 8efbf65db. Discovery found an NVIDIA GeForce RTX 3050 6GB Laptop GPU with 6,144 MiB VRAM. No alternative model was needed for the controlled acceptance probes.

| Request or transition | Implemented behavior |
| --- | --- |
| Calculator, PC command or other supported direct action | Existing deterministic handler bypasses model generation. Verified action acknowledgements remain grounded in execution results. |
| Ordinary conversation or short explanation | Automatic routing selects the installed fast profile. |
| Complex application, research comparison, technical design or full-history analysis | Existing heuristic tier router selects the thinking profile without an extra classification model call. |
| Fast backend unavailable or fails before visible output | Fall back to thinking once; missing-model status is visible. Never replay an answer after partial visible output. |
| A simple turn after complex work | Re-evaluate the next request and return to fast selection. No permanent escalation. |
| User changes generative GGUF or local Ollama tag | Persist the fast selection separately in Settings → Models; apply it to subsequent requests. Automatic selection can be disabled. |
| Concurrent generation or model change | Serialize the full local generation lifetime under the existing LOCAL_MODEL/GPU/VRAM admission boundary. Close evicted in-process models. |
| Residency | Swap on demand, one model configuration at a time; existing server fit, VRAM margin and CPU offload remain available. |

Text deltas continue through the existing UI streaming path. SemanticChunker can deliver bounded speakable chunks before completion, using the same VoiceRuntime and barge-in cancellation machinery. No physical microphone, speaker or paid ElevenLabs request was exercised for this release's live model probe; first-audio latency is not certified.

## Current-chat memory (items 23–37)

The same knowledge database now holds `research_chat_messages`, `research_chat_index_state`, `research_chat_summaries` and the external-content FTS5 `research_message_fts` index. Messages have stable IDs, chat IDs, monotonic sequence, role, exact text, timestamps, revision and attachment metadata. SQL triggers keep FTS and summary invalidation aligned with writes/deletes. Foreign-key cascades remove chat-owned rows. Legacy compressed archives retain checksum validation and migrate lazily without losing names, protection, retention or project links.

The UI saves windows transactionally and appends only new messages. It loads 160 recent messages for recovery, bounds the working model history and renders at most 100 message widgets. Older and newer pages remain retrievable from the database. Stable source references let search results and grounded replies jump to the original message window. New output is retained while the reader scrolls earlier; streaming no longer repeatedly forces the bottom position.

Retrieval combines BM25 lexical ranking, a small documented query-expansion dictionary, first/latest intent, role filtering, neighboring message windows, day filters and early/middle/recent timeline clusters. Every fetch/search/window/range requires a chat ID; Kernel history capabilities require the authoritative ExecutionContext conversation ID and re-read the source text/revision during verification. Earliest and middle messages are indexed independently of the recent prompt window. Chronological queries preserve old statements for historical questions and expose newer corrections for present choices.

**Semantic status:** embeddings are not installed or validated. The lexical, expansion and chronological fallback works independently. This is not a certified embedding/hybrid-vector backend. Wordless paraphrases outside the small expansion dictionary may miss a source. Decision/correction retrieval uses keyword candidates, not a complete semantic interpretation of every discussion.

Summaries are bounded, versioned, source-linked extracts of the first two and recent eight messages. They require no inference and invalidate when sources change. They supplement source retrieval; they do not replace the retained transcript or establish facts by themselves.

Context assembly includes bounded recent turns, relevant current-chat source windows and a smaller approved-preference section. It excludes the current query from historical evidence. Retrieved messages are explicitly quoted historical data. Missing evidence prompts a truthful inability to verify, rather than inventing a memory. ContextManager bounds auxiliary data; the installed server's apply-template/tokenize endpoints check difficult Unicode prompts against the actual token budget. Unsupported token endpoints use a conservative UTF-8 byte bound. No whole-chat injection is required.

## Personal preferences, privacy and controls (items 38–57)

Personal Memory defaults off and is independent of current-chat search. The existing MemoryManager records now include category, contextual preference key, consent/proposal state, provenance IDs, scope, timestamps, expiry, supersession and explicit-capture status. Categories cover response style, explanation, technical preference, project context, stable choices, recurring workflow and explicit user memory.

Explicit user statements can save a preference after enabling the feature. Contextual corrections replace the applicable preference rather than stacking contradictory rules. Optional repeated-feedback suggestions remain proposals until approval; there is no autonomous extraction model or silent conversion of old legacy records into approved preferences. Deduplication separates general, coding and science contexts. Current explicit instructions override older style data.

Retrieval applies only approved, active, unexpired, relevant records under user, project or conversation scope. Project records require the matching project; private/session-retention chats do not save or use personal preferences. Deleting a message invalidates derived preferences; deleting a chat removes chat history while independently approved preferences have their own controls. Forgetting a preference tombstones its source IDs so replaying that old source cannot silently recreate it. Clearing/exporting are explicit actions. Export JSON is readable and should be handled as personal data.

New preference payloads use the existing Windows DPAPI SecureVault protection, atomic local writes and rollback on failed persistence. Legacy memory behavior remains available to its existing explicit search surface. Raw chat history retains the existing local database security model; this update does not claim whole-database encryption. Secret screening rejects recognized API/OAuth tokens, passwords, private keys, pairing codes and sensitive personal details, and prompt snippets redact recognized credentials. Heuristic screening is not a proof that every possible sensitive phrase can be recognized. No automatic external synchronization was added.

Documents, websites, devices, connectors and assistant messages cannot establish preferences. Memories cannot grant tools, permissions or policy changes. Context text and workflow packets label retrieved data untrusted; the existing Kernel and permission brokers still decide what may execute.

Settings → Memory exposes real flags and stored records, search, category/scope, propose/approve, correction, forget, clear confirmation, export, current-chat search and diagnostics. History search supports first/latest/timeline and source jumps. Storage diagnostics show indexed counts, database bytes, rebuild time and retrieval latency. The existing History controls govern chat retention.

SQLite transactions preserve old searchable state if rebuild is cancelled or fails. Index rebuild reconstructs FTS from retained message rows or safely decoded legacy archives. Losing derived index-state metadata no longer erases the authoritative rows. Stable IDs, bounded recent reload and existing recovery services support crash/restart. Legacy messages without per-message timestamps use archive creation time; their date filters are approximate. Incremental messages record their actual save time.

## Measurements and acceptance evidence (items 58–69)

The committed [benchmark evidence](evidence/fast-memory-benchmark-0.9.5.json) contains controlled synthetic fixtures and actual local inference. Each history size used 30 indexed queries with known facts at the start, positions 50/500, middle and end, plus a separate scope. These accuracy numbers describe those fixtures only.

| Messages | Search p50 / p95 | Top-1 / scope leaks | Bounded reopen | Append | DB bytes | Rebuild |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.610 / 0.664 ms | 100% / 0 | 12.03 ms | 9.20 ms | 421,888 | 11.99 ms |
| 10,000 | 0.610 / 0.712 ms | 100% / 0 | 11.90 ms | 8.74 ms | 2,908,160 | 27.45 ms |
| 100,000 | 0.664 / 0.761 ms | 100% / 0 | 12.93 ms | 9.86 ms | 28,852,224 | 219.40 ms |

Initial indexing of 100,000 messages took 4.90 s, about 289 DB bytes/message. The startup column in raw benchmark JSON measures opening the database/store (about 172–176 ms), not complete application launch. It does not extrapolate 1,000-message costs to 100,000 messages.

| Actual inference scenario | First visible token | Backend preparation | Observed GPU allocation |
| --- | ---: | ---: | ---: |
| Fast cold | 6,398.90 ms | 4,924.27 ms | 3,641 MiB |
| Fast warm, cached short prompt | 75.89 ms | 19.37 ms | 3,641 MiB |
| Thinking after switch | 10,128.29 ms | 9,465.74 ms | 4,015 MiB |
| Fast after switching back | 5,799.35 ms | 5,306.96 ms | 3,641 MiB |

Cancellation yielded zero additional text chunks after the first accepted chunk, returning in about 50 ms. Unload took about 437 ms and the probe observed GPU allocation return to zero. These samples are not a throughput comparison: prompts and completion lengths differ and the warm prompt reused cached tokens. Actual fitted GPU layer counts are not reported as a fabricated fixed number.

The [live acceptance evidence](evidence/fast-memory-live-0.9.5.json) requires actual source IDs for first-message and latest-correction cases. It retrieved Project Orion across 10,002 messages, answered blue from the newer correction, declined a nonexistent fact, and respected a current one-sentence instruction over a saved detailed-coding preference. After the model-lock repair, the first speakable chunk was ready at 377 ms while generation finished at 2,270 ms. This measures chunk readiness, not physical audio playback.

No new periodic memory inference or embedding worker runs at idle. Idle CPU, process RSS and physical end-to-end voice latency were not measured as standalone performance claims. The available GPU observations and database storage measurements above are the measured resource evidence.

## Regression, packaging and release (items 70–77)

Added tests cover 10,001-message exact recall, early/middle/recent positions, original/latest/timeline, scope denial, source re-verification, safe legacy migration, missing-index recovery, edit/delete invalidation, cancellation/rebuild, encrypted persistence, approval/correction/forget/export, private chats, secret and authority rejection, untrusted sources, current-instruction precedence, model routing/fallback/serialization, bounded Unicode context and native Qt settings/source jumps/scrolling during streaming. Parallel-agent tests verify matching conversation identity and bounded provenance-labelled packets.

Targeted runs passed: 178 tests for the initial integrated backend/UI/research set; 121 tests after the recovery and workflow changes; 95 tests after the natural latest-decision query fix; 70 model/resource tests after repairing same-thread stream re-entry; and 11 native UI/resource tests for the final memory controls. The final full suite, frozen startup and package audit results are recorded below when complete. An earlier baseline run exposed a full-suite Qt rich-text timing failure that passed in isolation. A subsequent full run exposed a same-thread model-lock wait; the fix returns busy immediately while preserving cross-thread serialization. Superseded runs and binaries were not accepted for release; final release gating requires a clean full run and exact frozen-source parity.

Release assets use a separate model-free PyInstaller candidate and a versioned `release/v0.9.5` directory, preserving previous releases and the current private dist app during validation. Installer input can explicitly select the verified candidate. Frozen bytecode/public-asset parity, isolated native startup, clean installed wheel startup, archive integrity, package contents and checksums gate promotion. GGUF weights, credentials, real user history and private test logs are excluded. Existing Vosk voice data remains intentionally bundled.

The user explicitly authorized a new release, repository information updates, and subsequently the website download-link publication. Publication and local dist promotion are recorded with exact receipts. The final local promotion happens after publication, preserving existing local model files and retaining a reversible backup.

Remaining limits are the optional embedding backend, heuristic retrieval/secret screening, approximate dates for legacy archives, model hallucination risk despite source context, cold swap latency, and unmeasured physical voice/RSS/idle metrics. No guarantee of perfect recall or arbitrary-model compatibility is implied.

Final local validation record:

| Gate | Result |
| --- | --- |
| Complete isolated Python regression | **1,225 passed; 62 subtests passed**, 581.86 s. |
| Application source SHA256 | `0f9edd40663a8a52d721a0f22c1132c5684b6e6bc730685f9882fa44ffa8c04c` |
| Test source SHA256 | `5e52ebb1b7257d2f6d14b9ee884b90c39b0b9aff1b64e385feb6c469ddf33646` |
| Frozen archive parity | 219 application modules equal current source; required public assets equal; no GGUF/user state/secrets. |
| Frozen executable SHA256 | `966447864ea5660f58d505c3c8713bea2bb48a3f0db7a15687e15eb22975345c` |
| Frozen native Windows startup | RenovatedWindow; 101 UI ticks; no critical failures; clean shutdown; zero resource leases. |
| Fresh installed-wheel native startup | 299 installed source/asset files equal wheel; no critical failures; clean shutdown. |
| Python wheel/sdist metadata and contents | Twine passed; ZIP/tar integrity and exclusion/credential scans passed. |
| VNext | 14 tests passed; TypeScript typecheck passed. |
| Website | Production build passed with the approved 0.9.5 download link. |
| Windows packages | Model-free portable ZIP built/tested; Inno Setup compiler succeeded. Setup requires both its EXE and matching `-1.bin`. |

The first GitHub full run aborted in native garbage collection after installing Qt 6.12. Its stack did not report a failed application assertion. The packaged application and successful local full suite use Qt 6.11.2. Python dependency metadata and requirements now pin **PySide6 6.11.2** so source/wheel installs use that tested native version. The Qt 6.12 abort is an observed compatibility limit, not a claim that a specific upstream defect has been proven. A fresh pinned-wheel startup and repeated GitHub regression gate the final release.

Receipts are in [evidence](evidence/). Release-wide archive/content scans and the final checksum manifests accompany the [0.9.5 release](https://github.com/EONASH2722/MORICE/releases/tag/v0.9.5). The installer was compiled from the verified candidate; installation into a real user profile is not claimed as an automated test. The source and documentation archives include this report.

Source-control status at report generation: the implementation and controlled evidence are staged on `main`; commit, push, tag and release publication are explicitly authorized. Publication is gated on the local checks above and successful GitHub CI/package validation. The final release tag identifies the published commit. The approved website change publishes with this source update. The validated candidate is then promoted to the private local dist app, preserving its existing model files.

Storage cleanup preceded implementation as requested: old generated builds were reversibly archived from E: to D:, reclaiming 16.26 GiB in the initial cleanup. Source, user data and current model files were preserved. Superseded 0.9.5 candidates were also archived instead of retaining duplicate build copies on E:.

New files: `memory_policy.py`, `ui_next/memory_view.py`, two fast-memory test modules, benchmark/live-probe scripts, this report, architecture audit, memory guide, release notes and controlled JSON evidence. Modified files include history, MemoryManager, model/context/router/runtime owners, native chat/settings/workspace UI, calculator and conversation policy, package smoke, agent context/packet plumbing, parallel tests, version/installer metadata, README/changelog/docs and the approved website version link. Git history contains the authoritative full file list.
