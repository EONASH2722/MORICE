# Fast replies and dual memory: pre-change architecture audit

Audited 2026-10-22 against the clean 0.9.4 main checkout in E:\MORICE.

* RuntimeServices owns AgentOrchestrator, the Capability Kernel, shared resource leases, DesktopIntegrationLayer, RealtimeIntelligence, research and background work. Extend these owners.
* AgentOrchestrator already owns ModelRouter and ContextManager. RealtimeIntelligence's TieredModelRouter already classifies reflex/general/deep requests without inference. Connect its decisions to actual providers; do not create another scheduler or conversation engine.
* llm_client streams through an owned llama-server or local_llama and already obtains LOCAL_MODEL/GPU claims. The server owns one model configuration, but the in-process cache can retain multiple models and has no generation lock. Serialize complete generations and close evicted models under the shared admission boundary.
* Actual saved model_path/model_name are empty. The application launcher resolves E:\MORICE\Parable-Qwen3-4B-Claude-Fable-5-GGUF-Q5_K_M.gguf (2,889,513,280 bytes), context 8192. A direct backend import without the launcher instead falls back to Qwen2.5-Coder-7B-Instruct-abliterated-Q4_K_M.gguf; the launcher is authoritative for the shipped application. Preserve reasoning selection and sampling.
* GPU discovery: NVIDIA GeForce RTX 3050 6GB Laptop GPU, 6144 MiB. Existing llama-server supports fit/CPU offload and a reserved VRAM margin. Use swap on demand with one admitted generation.
* Research ChatHistory uses the existing knowledge SQLite database, stable chat IDs, metadata and checksummed compressed transcripts. It currently strips message IDs and only indexes chat names, while UI/model context uses a recent window. Add message rows/FTS and safe lazy archive migration in this same database.
* DesktopIntegrationLayer already owns MemoryManager, a bounded local record store with user/project/session scopes, atomic writes, search, edit/archive/delete/export and an enabled flag. Extend records with consent, provenance and contextual preferences; never promote old unapproved records implicitly.
* PySide MainWindow keeps history, uses deterministic PC/math routes before model work, handles cancellation epochs, streams visible tokens and sends bounded speakable chunks to VoiceRuntime before generation finishes. Preserve these paths and add memory at context construction.
* Renovated SettingsWorkspace moves existing controls into searchable categories. Add fast-model selection and a Memory category here. History navigation should page message windows rather than instantiate every retained message.
* Packaging: MORICE.spec collects morice subpackages; models are optional and excluded by default. build-release.ps1 currently clears the release directory: do not run its destructive cleanup over previous releases. Build 0.9.5 into a versioned release directory instead.
* Tests: pytest through scripts/run_isolated_tests.py isolates settings, runtime and Qt from user data. VNext has tests/typecheck. Existing archive integrity and retention tests must stay meaningful.

The implementation and measured evidence are documented in fast-memory-report-0.9.5.md. Publication is explicitly authorized by the user's release request. Model acquisition was explicitly authorized in the follow-up; weights remain outside the repository and release assets.
