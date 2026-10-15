# Generative Media Lab — Phase 9

Phase 9 extends the existing MORICE runtime. `RuntimeServices.media` lazily creates `MediaLab` using that runtime's `CapabilityKernel`, `AgentCoordinator`, scheduler, permissions, events and `ResourceManager`. The existing nine agent roles remain; the vision role can invoke media capabilities. There is no second graph engine, agent pool, permission controller or verification engine.

## Admission and execution

`MediaLab.submit(ImageRequest | VideoRequest, ExecutionContext)` returns a generation ID and a future. The existing Kernel scheduler prepares jobs and reserves resources before submitting execution to its bounded shared pool. Resource waits occur on a short-lived admission thread. The global deferred queue and media queue each reject more than 32 pending jobs. Priority aging prevents new foreground submissions from indefinitely displacing older background work. Cancellation and deadlines apply while queued and executing. Simple calculator, command and deterministic actions retain their existing direct path.

Every local generation requires exclusive `GPU` and `LOCAL_MODEL` leases, shared `CPU` and `DISK` claims, and dynamic `VRAM_MB` and `RAM_OFFLOAD_MB` claims. The planner uses actual NVIDIA telemetry, system RAM, disk space and power status. Defaults retain 768 MiB VRAM and 2048 MiB available RAM. Estimates are conservative and can reject a configuration even if a different implementation might fit. Unknown telemetry refuses allocation.

Active chat/model leases cause media to wait. Under the exclusive media fence, MORICE may unload its own idle llama.cpp/cache weights and then remeasure both RAM and VRAM. Foreign services are never stopped. Native GPU vision also shares the GPU/model fence. Idle vision or external model residency can still reduce available headroom; there is no automatic termination of those unrelated workloads.

Diffusers inference runs in an owned external Python process. The desktop imports no Torch, Diffusers or Transformers at startup. On Windows, RAM telemetry sums the launcher and its child processes. The process owner tracks descendant identities, checks RAM margins, bounds logs and reaps workers/encoders on cancellation, crash or deadline. Unconfirmed physical cleanup retains shared leases and produces a dirty shutdown instead of claiming success.

An OOM is recorded against the model hash, hardware/driver, backend version, settings, mode and admitted VRAM budget. With explicit `allow_fallback=True`, one smaller retry may run after the failed worker is reaped. It cannot increase the original resource claims. Metadata preserves requested and actual settings. Without that option, the failed job remains failed.

## Models and backends

Image and video descriptors include architecture, backend, source/license, precision, quantization, resource estimates, tested dimensions/frames, workflow support, dependencies, hash and version. Model states are DISCOVERED, AVAILABLE, DEGRADED, MISSING_DEPENDENCY, INCOMPATIBLE, DISABLED, FAILED_HEALTH and UNBENCHMARKED. File existence never establishes loadability. Each model is represented in the shared Kernel inventory. Restart requires a fresh health/integrity inspection.

Discovery is explicit, shallow and bounded. Inspection validates safetensors headers and hashes all bundle files. Execution rechecks those hashes in the parent and isolated worker. The adapter accepts reviewed upstream Stable Diffusion, SDXL and Stable Video Diffusion pipeline classes, not arbitrary model code. Pickle/checkpoint Python execution, custom pipelines, `auto_map`, remote code and automatic custom-node installation are refused. Quantized diffusion bundles and LoRAs are not validated in this implementation.

The real tested image model is **Stability AI SD-Turbo fp16**, pinned to `b261bac6fd2cf515557d5d0707481eafa0485ec2`. The user approved its exact 2,581,668,541-byte manifest before download. Its three safetensors files were verified against upstream LFS SHA256 values. Weights and the external Python environment remain under `E:\MORICE_DATA`, outside the repository and package. See the pinned local license and [the upstream model repository](https://huggingface.co/stabilityai/sd-turbo/tree/b261bac6fd2cf515557d5d0707481eafa0485ec2). No license or redistribution entitlement is inferred from a successful download.

The optional ComfyUI adapter requires an explicitly configured dedicated loopback service and checkpoint directory. It implements a reviewed PNG text-to-image core-node graph through `/prompt`, `/history`, `/view` and owned prompt cancellation. Redirects and custom nodes are rejected. The adapter requests model release through `/free` and verifies reported CUDA allocator memory before releasing leases. These endpoints follow the [official ComfyUI server implementation](https://github.com/Comfy-Org/ComfyUI/blob/master/server.py). Controlled HTTP fixtures validate the contract; no installed ComfyUI model was tested on this machine.

The reviewed Diffusers adapter supports text-to-image, sequential seeded variations, image-to-image, mask-preserving inpainting and centered outpainting. PNG, JPEG and WebP are supported. Independent upscale/background-removal models, LoRA/control guidance and arbitrary custom workflows remain unavailable. Optional SVD image-to-video adapter code exists, but no approved compatible video/motion model is installed here. **VIDEO PROVIDER UNAVAILABLE** is the truthful local status. SVD's text prompt is recorded as intent, not falsely presented as conditioning.

## Artifacts, history and recovery

Successful images must fully decode, match dimensions, satisfy pixel/channel/byte limits and have nonconstant content unless minimalism is explicitly allowed. GIF verification decodes every frame and checks dimensions, count, duration and requested motion. MP4/WebM require actual ffmpeg/ffprobe encoding and decoding; neither tool was found on this machine. An image with a video suffix is never accepted.

The existing Kernel verification contract hashes and decodes outputs again. Atomic publication happens while resource leases remain held; only the subsequent successful Kernel completion commits the visible SUCCEEDED history record. Failed, cancelled, interrupted or uncommitted outputs are excluded from the artifact API. Exports use existing file-write permission checks, atomic creation and hash verification, and refuse overwriting a different destination.

History is a bounded SQLite store outside the chat transcript. It records prompt, seed, requested/actual settings, model identity/hash, backend version, hardware, timings, RAM/VRAM measurements, warnings and artifact hashes. Seed reproducibility is scoped to compatible versions, hardware and deterministic backend behavior. Process exit is the final guarantee of CUDA residency release; allocated VRAM before exit can include small generator buffers.

Restart marks unfinished jobs INTERRUPTED and never replays them. New workers persist exact PID/creation-time ownership records. Interrupted temp directories are removed only when every recorded process identity is gone. Live processes, absent ownership proof and inaccessible identities remain quarantined and visible in diagnostics. Model weights and completed outputs are not automatically deleted. Older interrupted temp files without ownership records require explicit review.

Contact sheets derive only from verified local artifacts. The cache has a configured size limit and evicts only MORICE-named derived previews. Cache clearing preserves user files, original outputs and models. `storage_stats()` reports bounded directory totals and registered model manifest sizes; a truncated scan is explicitly labeled.

## Cross-phase integration and Phase 10 API

Builder asset requests use the same Kernel/agent runtime. Verified exports attach an asset/source/license/hash manifest to the existing project session. Research diagrams carry `GENERATED_VISUAL`, cannot masquerade as MEASURED data, and cannot become scientific evidence. Ambient consumes existing media queued/started/completed/failed/cancelled/OOM events and its existing notification/deduplication policy.

Remote requests use the existing Device Mesh protocol and exact node pinning. They cannot silently fall back locally or upload reference files implicitly. Remote artifacts need an explicit hash-verified Mesh transfer before local use. The validation is a complete paired TLS protocol fixture, not proof of a physical second GPU or remote production generation.

Public surfaces for the Phase 10 Media UI are `submit`, `cancel`, `models`, `inspect_model`, `discover`, `plan_request`, `history`, `result`, `artifact`, `export`, `contact_sheet`, `clear_derived_cache`, `storage_stats`, `update_settings`, benchmark tickets and `status`. DTOs and metadata use schema 1. `status.load_state` exposes NORMAL, GPU_BUSY, VRAM_PRESSURE and MEDIA_GENERATING. No Phase 10 UI redesign is included.

FAST uses bounded default steps, BALANCED uses model defaults, QUALITY increases defaults within the model's validated step ceiling, and MAXIMUM_THAT_FITS selects only successful current benchmark configurations that match workflow/model/hardware/backend and fit live margins. Aesthetic quality remains a user judgment. Explicit settings override presets. Benchmarks increase bounded image resolutions from 512 to 640 to 768 and video frames from 8 to 16 when an approved model exists; unavailable configurations are recorded rather than forced.

The `morice-media` CLI exposes status, discovery, inspection, generation and benchmarking. The generation API never downloads a model or installs dependencies. The approved one-time download script is separate and requires explicit approval.

## Validation boundaries

Detailed numbered results and remaining constraints are in `generative-media-lab-report.md`; the final independent audit is in `generative-media-lab-audit.md`. Actual media evidence, controlled failure fixtures, protocol fixtures and prior phase evidence are distinguished there. Optional providers and workflows without real model validation are not claimed as validated capabilities.
