# Models And Performance

MORICE separates model inference from host execution. A model supplies language, coding output, or typed instructions; the application still validates renderers, project manifests, paths, permissions, and sensitive actions.

## Supported Sources

### Local GGUF

Use **Panel > Change model** and select a `.gguf` file. MORICE checks that the selected file is a plausible GGUF model before saving it. Non-model files are rejected even if they are large or renamed.

The local llama server exposes an OpenAI-compatible loopback endpoint internally. This is a local runtime detail, not a hosted-provider integration.

On supported NVIDIA systems, MORICE prefers its installed CUDA llama runtime and automatically fits GPU layers/context to available VRAM. The selected GGUF is prewarmed in the background after the window opens, so the first user turn does not pay the full cold-load delay. Set `MORICE_DISABLE_MODEL_PREWARM=1` only when startup model loading is undesirable.

### Local Ollama

Enter an installed Ollama model tag in the model control. MORICE queries the local Ollama service and uses its chat/generate endpoints. Install and pull models with Ollama itself before selecting them in MORICE.

### Cloud Providers

General hosted OpenAI, Anthropic, Gemini, or third-party conversational LLM configuration is not part of `0.8.0`. ElevenLabs reply speech and source-linked web retrieval are separate optional network features, not hosted reasoning providers.

## GPU Detection

**Detect GPU** gathers local adapter and VRAM information and generates a conservative run plan. It is an estimate: context length, quantization, GPU layers, driver allocation, display usage, and other applications all affect memory pressure.

| VRAM | Suggested starting configuration |
| ---: | --- |
| 0-3 GB | CPU-first; short context; small partial offload if stable |
| 4 GB | Partial offload and conservative context |
| 6 GB | Balanced target for the release Qwen2.5 Coder 7B Q4 model |
| 8 GB | Full-offload target with moderate context headroom |
| 12 GB+ | Longer context or a larger compatible quantized model |

System RAM still matters. CPU-first inference should have enough free RAM for model weights, context, the application, and operating-system overhead.

## Choosing A Model

- Prefer coding-tuned models for Project Mode.
- Prefer instruction-tuned general models for broad chat.
- Smaller or more heavily quantized models answer faster but may produce weaker project manifests and reasoning.
- Larger contexts consume more memory and can slow prompt processing.
- Model maturity does not bypass renderer accuracy checks or project permissions.

## Troubleshooting

**The model is rejected:** verify the file is a complete GGUF, not a download page, archive, JSON metadata file, or partial transfer.

**The model loads but replies slowly:** lower context, reduce GPU layers, close GPU-heavy applications, or select a smaller quantization.

**Ollama is unavailable:** start the local Ollama service and confirm the model appears in `ollama list`.

**The model gives invalid project JSON:** MORICE keeps the proposed workspace unchanged and may offer its limited local fallback builder. Select a coding model or simplify the request.

**Changing models changes renderer output:** the model may choose different instructions, but the host renderer remains deterministic for the accepted artifact. Include explicit equations, values, units, and requested view when accuracy matters.
