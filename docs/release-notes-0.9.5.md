# MORICE 0.9.5 — fast replies and memory

Download the portable ZIP and extract it fully, or download **both** the Setup `.exe` and its matching `-1.bin` into the same folder before running Setup. Verify the files against `SHA256SUMS.txt`. Model weights are separate downloads.

Python installs pin PySide6 6.11.2 to match the tested Windows runtime. Qt 6.12 encountered a native cleanup abort in the initial CI environment.

MORICE can now use separate fast reply and thinking models automatically. **Settings → Models** lets you change the fast GGUF file or installed Ollama tag without replacing the thinking selection. Installed Qwen3-4B-Instruct-2507 Q4_K_M is the preferred fast profile. Simple commands still use deterministic tools. Complex work uses the thinking profile; a failed fast backend can escalate before any answer is displayed.

Retained chats now have indexed messages, stable IDs and sequence positions in the existing knowledge database. Search the entire current chat, retrieve its beginning or a decision timeline, and jump to original messages. Opening a chat loads a bounded recent window. Source edits, deletions and retention invalidate the corresponding searchable data.

**Settings → Memory** adds optional personal preferences, disabled by default. Save a preference explicitly, review a suggestion, correct or forget a record, select chat/project/personal scope, and export approved records. Current instructions override old preferences. New preference records use Windows DPAPI protection; exports are readable JSON. Credentials and sensitive details are rejected, and external documents cannot establish preferences. Session-retention chats do not save or apply personal preferences.

Chat scrolling preserves the reading position while loading older pages. Streamed replies stop forcing the viewport to the bottom. New output can finish while you read earlier messages and remains available when you return.

The existing 0.9.5 release also includes the duplicate-message repair: personalized streamed replies retain their saved message IDs, so scrolling cannot load the same answer as another bubble. Returning to the latest saved reply reuses its row. Identical answers in separate turns remain separate. Informal questions such as “whats the date today” use the local system clock.

The existing Kernel, agents, verified actions, Builder, Research, Device Mesh, media, spatial tools and voice pipeline remain the execution authorities. Local generations share one model lifecycle and the existing resource leases. Model weights are installed separately from release packages.

Measured on an RTX 3050 6 GB laptop: warm fast replies reached their first visible token in approximately 76–96 ms in short controlled samples. Cold load and model switching still cost several seconds. Controlled 100,000-message indexed retrieval stayed below 1 ms p95 in the recorded run. These are local fixtures, not a guarantee for arbitrary prompts, storage or hardware.

See the [guide](fast-memory-guide.md), [architecture audit](fast-memory-architecture-0.9.5.md) and [implementation/validation report](fast-memory-report-0.9.5.md). Embedding-based semantic search and physical microphone/ElevenLabs first-audio latency are not certified by this update. No end-of-life designation is made.
