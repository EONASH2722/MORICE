# Frequently Asked Questions

## Is MORICE fully offline?

Local GGUF/Ollama chat, deterministic renderers, project files, notes, and local services can operate without web lookup. Model downloads, trusted catalog browsing, Online+local context, and update checks require network access.

## Which models can MORICE use?

The current release supports validated local GGUF files and locally installed Ollama models. General hosted-provider API keys are not integrated.

## Does changing the model change visualization accuracy?

The model may produce a different instruction, but MORICE builds and validates the accepted artifact itself. Explicit equations, values, units, and object names produce the most reliable routing. Unsupported requests fail visibly.

## Can MORICE render every science or engineering concept?

No. It has nine deterministic renderer families with curated subtypes. It is not a general CAD, CFD, medical, quantum-chemistry, or molecular-dynamics system. Check the [feature matrix](feature-matrix.md).

## Are component schematics manufacturing-accurate?

No. They are labeled educational and use validated primitive layouts. Numerical graph/simulation invariants receive stricter accuracy tests, but generic schematics are not certified CAD.

## Why did a molecule fail to render?

Chemistry uses a curated structure library. Unknown molecules are rejected instead of receiving invented coordinates.

## Can Project Mode use any language?

It can propose and write arbitrary text-based source files. A runnable result still depends on the selected coding model, prompt, installed compiler/SDK, dependencies, and local platform. The built-in fallback builder supports a smaller subset of web patterns.

## Does Full access remove approvals?

No. It expands eligible paths. Protected locations, manifest validation, plugin isolation, and confirmation for sensitive actions remain active.

## Why does MORICE start with an empty chat?

That is intentional. Visible chat sessions start clean. Scoped memory, project state, recovery records, and settings persist separately and can be managed through Tools.

## How much VRAM is required?

The release Qwen2.5 Coder 7B Q4 lane targets 6 GB VRAM for a balanced setup, but it can run CPU-first or with partial offload on smaller GPUs. Context length and competing GPU applications change the real requirement.

## Can MORICE wake on a poor microphone?

Adaptive gain, noise-floor calibration, and diagnostics improve weak/noisy input, but the app still needs a functioning microphone and Windows permission. Run `python diagnose-wake-listener.py` before enabling startup listening.

## Where should bugs be reported?

Use the GitHub bug-report template and include the release version, model source, exact prompt, reproducible steps, expected/actual behavior, logs, and screenshots when relevant. Report security vulnerabilities privately according to [SECURITY.md](../SECURITY.md).
