# MORICE Phase 2 Agent Architecture

Phase 2 moves external actions out of model prose and into a typed,
application-owned execution layer. A model can reason about a task and propose
structured work, but only a verified tool result can establish that an action
occurred.

## Request Pipeline

Every request receives an identifier and passes through the same ordered stage
contract:

1. Intent detection
2. Context retrieval
3. Conversation memory
4. Project context
5. Capability detection
6. Planning
7. Tool selection
8. Permission check
9. Execution
10. Verification
11. Result collection
12. Renderer selection
13. UI update
14. Final response

Stages are recorded as `pending`, `in_progress`, `completed`, `failed`, or
`not_applicable`. Diagnostics shows the current request without exposing hidden
chain-of-thought.

## Typed Contracts

`morice/agent_types.py` defines stable request, plan, tool, result, project,
action, permission, risk, and execution-stage contracts.

Every registered tool declares:

- unique ID, display name, and description;
- input and output JSON-compatible schemas;
- required permissions and risk level;
- supported platforms and executable dependencies;
- timeout and cancellation support;
- health status, version, and idempotency.

The executor validates registration, health, platform, dependencies, input,
permission, and output. Failed validation stops execution immediately.

## Permissions

Write and process tools require a one-use permission token. The token is bound
to a SHA-256 fingerprint of the tool ID and exact arguments and expires after a
short interval. Changing one path, command argument, or file body invalidates
the token.

Project Mode uses this contract as a review flow:

1. Validate model manifest semantics.
2. Validate every source file.
3. Generate a real unified diff without writing.
4. Display the pending patch.
5. Let the user apply or reject it.
6. Apply approved files atomically.
7. Verify bytes on disk.
8. Run project source verification.
9. Offer undo backed by saved pre-change bytes.

Path resolution rejects absolute paths and `..` escapes.

## Tools

The initial built-in registry contains:

- workspace filename/content search;
- bounded project indexing and relevant-source retrieval;
- project source and entry-point verification;
- patch preview, atomic patch apply, and undo;
- cancellable no-shell terminal execution;
- Git status, diff, branch listing, history, and blame;
- approval-gated Git stash, restore, checkout, commit, and push.

Read-only successful actions are replayable. Mutations and failed actions are
not replayed automatically.

## Action History

Every attempt is stored in bounded JSONL history, including refused permission
checks and validation failures. Records contain timestamp, tool, exact
parameters, duration, success, verification, changed files, generated files,
artifacts, errors, replay eligibility, and undo ID.

Diagnostics exposes the recent timeline. Logs also receive structured agent and
agent-tool events.

## Project Index

The indexer avoids generated dependency directories and symbolic-link
traversal. It records:

- files, sizes, modification time, language, and content digest;
- Python classes, functions, and imports plus common cross-language symbols;
- frameworks, dependencies, build systems, and entry points;
- assets and configuration files;
- current Git branch, status, and recent commits;
- request-relevant files using bounded lexical semantic scoring.

Only bounded relevant source content is sent to the coding prompt. The full
repository is not blindly copied into model context.

## Models And Context

The router assigns general, coding, reasoning, or vision profiles and ranks
available models using speciality aliases plus observed health. It tracks
latency, failures, success rate, prompt and generated token estimates,
throughput, context usage, temperature, and GPU layers.

The context manager reserves space for the current request, settings, and
project data. It selects relevant recent turns and compresses omitted older
turns into a bounded factual summary.

The existing GGUF/Ollama runtime remains the final local inference backend and
retains its endpoint and model fallback behavior.

## Threading And Failure Behavior

Project indexing, command execution, Git reads, patch application, undo, and
project verification can run outside the UI thread. Terminal processes have
timeouts and can be terminated from the Project Output panel.

Tool failures preserve stdout, stderr, exit status, warnings, and errors.
Idempotent read tools may retry once. Write tools never retry automatically.
MORICE reports failure when verification fails and does not convert missing
output into a success claim.

## Current Limits

- The Project Output panel currently provides one active command lane rather
  than a full PTY with several simultaneous tabs.
- Project source verification performs deterministic static validation and
  entry-point detection. Framework-specific test/build commands remain
  explicit user-approved terminal actions because arbitrary package scripts
  can execute code.
- Cross-language indexing extracts common declarations and imports but is not a
  compiler-grade call graph for every language.
- Model routing chooses among models already configured or available to the
  app; it does not silently download a specialist model.
- Package installation, registry modification, process termination, and
  system-setting mutation are intentionally unavailable until dedicated tools
  with preview, rollback, and explicit confirmation are implemented.

These limits are reported rather than hidden behind simulated output.
