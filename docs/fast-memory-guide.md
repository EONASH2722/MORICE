# Fast replies, chat recall and preferences

## Choose models

Open **Settings → Models**. Keep the thinking GGUF or Ollama selection in the existing model controls. Use **Change fast reply model** to select another local GGUF, or enter an installed fast Ollama tag. **Use Qwen default** clears the custom fast selection and discovers `models/llm/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` under the configured `MORICE_LOCAL_DATA_DIR`.

With automatic selection enabled, conversation and straightforward explanations use the fast profile; complex technical design, application building, derivations and difficult historical analysis use thinking. Simple follow-ups can return to the fast profile. If a fast profile is unavailable, MORICE uses the thinking profile and reports that state in model settings. Turning automatic selection off uses the thinking selection for all model-backed replies.

The preferred upstream is [Qwen/Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507). The tested conversion is [Unsloth Q4_K_M](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/blob/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf): 2,497,281,120 bytes, Apache 2.0, SHA-256 `3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597`. Download it only when you choose to install it; normal release packages contain no GGUF weights.

The installed CUDA llama-server is preferred where available. Generations use one shared lifecycle and the Kernel's existing LOCAL_MODEL/GPU/VRAM leases. A different model waits for the active generation to finish. The backend fits layers/context with its existing VRAM margin and can offload to CPU. The default policy swaps on demand rather than retaining both models in VRAM. Cold loads and swaps take seconds; a prewarmed fast model avoids that cost on ordinary turns.

## Recall this chat

Ask about the beginning, an earlier topic, the original choice or the latest decision. MORICE retrieves retained source messages, neighboring windows and chronological clusters. The current chat ID scopes every lookup. It does not search other chats automatically.

Open **History → Search all messages in this chat** or **Settings → Memory → Search this chat** for explicit search. Choose first/latest messages or a decision timeline. Double-click a result to jump to a bounded original-message window. Responses that used source snippets can also display original-message buttons. **Show latest chat** returns to the recent window.

The search layer uses SQLite FTS5, BM25, sequence selection and a small documented query-expansion dictionary. It is not an embedding model. If no source supports the requested fact, MORICE is instructed to say it could not verify that memory. For exact quotes, source text remains authoritative.

Earlier pages load as you scroll toward them. New streamed output no longer drags you away from the text you are reading. The UI keeps at most 100 live message rows; retained source history stays in SQLite and can be paged or searched. Old compressed archives migrate safely on access. Migrated message timestamps use the archive creation time because those archives did not record per-message times.

## Personal preferences

Personal Memory is off by default. Enable it in **Settings → Memory**, then say, for example, “Remember that for coding tasks I prefer detailed implementation steps.” Confirmation appears only after the record is saved. You can also add a record directly in Settings, select a category and choose personal, project or current-chat scope.

“Actually, I prefer shorter replies now” can correct an existing relevant preference. A current request such as “Answer in one sentence” overrides the older preference. Coding preferences apply to coding requests; project records apply only to the same selected project. Personal preferences are not injected into deterministic calculator or PC actions.

Optional suggestions recognize a few repeated direct feedback phrases after at least three matching user statements. Suggestions remain proposed until you approve them in Settings. A single situational request does not become an approved global preference. This is a bounded rule-based feature, not a general psychological profile or model-based extractor.

Use **Correct / approve selected** to edit or approve a record. **Forget selected** removes it and invalidates lookup immediately. Natural “Forget that preference” resolves the last preference explicitly saved in that session, or requests a more precise choice when ambiguous. The same forgotten source cannot immediately recreate its record. **Clear all preferences** requires confirmation and leaves chat history intact.

## Privacy and retention

New preference payloads are protected by the existing Windows DPAPI mechanism and kept locally. They are not synced automatically. Passwords, API/OAuth tokens, private keys, pairing codes and other screened sensitive details cannot be saved as preferences. Retrieved prompt snippets redact recognized credentials. Historical messages are quoted data and cannot grant permissions or alter tool policy.

Preferences can be reviewed and exported explicitly as readable JSON. Protect exported files and backups appropriately; another Windows account may be unable to decrypt the original DPAPI payload. Existing legacy memory records are not silently promoted to approved preferences.

Disabling Personal Memory stops new preference capture and injection. Current-chat search is a separate switch. Session-retention chats do not save or use cross-chat preferences. Deleting a chat deletes its indexed messages and summaries; independently approved personal preferences have separate deletion controls. Editing or deleting a source message invalidates a preference derived from that source. No new transcripts are duplicated into the legacy cross-chat knowledge graph by ordinary replies.

**Storage status** shows indexed-message/preference counts, database size and lookup timing. **Rebuild history index** reconstructs retained chat indexes transactionally; **Cancel index rebuild** stops it while preserving the previous index. Original messages, chat names, protection, archives, retention and project links are preserved.
