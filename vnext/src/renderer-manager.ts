import type {
  EngineResponse,
  WorkspaceArtifact
} from "./contracts";

export interface RendererCapability {
  readonly id: string;
  readonly label: string;
  readonly interactive: boolean;
  readonly dimensions: readonly ("2d" | "3d")[];
}

export interface RendererPlugin<TArtifact extends WorkspaceArtifact> {
  readonly capability: RendererCapability;
  canRender(prompt: string): boolean;
  build(prompt: string): Promise<TArtifact | null>;
  validate(artifact: TArtifact): readonly [valid: boolean, reason: string];
  estimateBytes(artifact: TArtifact): number;
}

export interface RenderProgress {
  readonly stage:
    | "analyzing"
    | "selecting"
    | "preparing"
    | "rendering"
    | "validating"
    | "ready";
  readonly percent: number;
  readonly detail: string;
}

export type ProgressListener = (progress: RenderProgress) => void;

interface CacheEntry {
  readonly artifact: WorkspaceArtifact;
  readonly bytes: number;
}

export class ArtifactCache {
  readonly #entries = new Map<string, CacheEntry>();
  #usedBytes = 0;

  constructor(readonly maxBytes = 256 * 1024 * 1024) {
    if (!Number.isFinite(maxBytes) || maxBytes < 1024 * 1024) {
      throw new Error("Artifact cache must be at least 1 MiB.");
    }
  }

  get usedBytes(): number {
    return this.#usedBytes;
  }

  get(key: string): WorkspaceArtifact | undefined {
    const entry = this.#entries.get(key);
    if (!entry) return undefined;
    this.#entries.delete(key);
    this.#entries.set(key, entry);
    return structuredClone(entry.artifact);
  }

  put(key: string, artifact: WorkspaceArtifact, bytes: number): void {
    if (!Number.isFinite(bytes) || bytes <= 0 || bytes > this.maxBytes) return;
    const previous = this.#entries.get(key);
    if (previous) {
      this.#usedBytes -= previous.bytes;
      this.#entries.delete(key);
    }
    while (this.#entries.size > 0 && this.#usedBytes + bytes > this.maxBytes) {
      const oldestKey = this.#entries.keys().next().value as string | undefined;
      if (oldestKey === undefined) break;
      const oldest = this.#entries.get(oldestKey);
      this.#entries.delete(oldestKey);
      this.#usedBytes -= oldest?.bytes ?? 0;
    }
    this.#entries.set(key, { artifact: structuredClone(artifact), bytes });
    this.#usedBytes += bytes;
  }

  clear(): void {
    this.#entries.clear();
    this.#usedBytes = 0;
  }
}

export class RendererRegistry {
  readonly #plugins = new Map<string, RendererPlugin<WorkspaceArtifact>>();

  register<TArtifact extends WorkspaceArtifact>(
    plugin: RendererPlugin<TArtifact>
  ): void {
    const id = plugin.capability.id;
    if (this.#plugins.has(id)) {
      throw new Error(`Renderer already registered: ${id}`);
    }
    this.#plugins.set(
      id,
      plugin as RendererPlugin<WorkspaceArtifact>
    );
  }

  get(id: string): RendererPlugin<WorkspaceArtifact> | undefined {
    return this.#plugins.get(id);
  }

  select(prompt: string): RendererPlugin<WorkspaceArtifact> | undefined {
    return [...this.#plugins.values()].find((plugin) => plugin.canRender(prompt));
  }

  capabilities(): readonly RendererCapability[] {
    return [...this.#plugins.values()].map((plugin) => plugin.capability);
  }
}

function cacheKey(rendererId: string, prompt: string): string {
  const normalized = prompt.trim().replace(/\s+/g, " ");
  let hash = 2166136261;
  for (const character of `${rendererId}\0${normalized}`) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `${rendererId}:${(hash >>> 0).toString(16)}`;
}

function errorResponse(message: string): EngineResponse<WorkspaceArtifact> {
  return { ok: false, message, recoverable: true };
}

export class RendererManager {
  constructor(
    readonly registry = new RendererRegistry(),
    readonly cache = new ArtifactCache()
  ) {}

  async render(
    prompt: string,
    progress: ProgressListener = () => undefined,
    signal?: AbortSignal
  ): Promise<EngineResponse<WorkspaceArtifact>> {
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) return errorResponse("The visualization request is empty.");
    progress({ stage: "analyzing", percent: 8, detail: "Analyzing request" });
    const plugin = this.registry.select(cleanPrompt);
    if (!plugin) {
      return errorResponse(
        "No validated renderer supports this request. Nothing was rendered."
      );
    }
    if (signal?.aborted) return errorResponse("Rendering was cancelled.");
    progress({
      stage: "selecting",
      percent: 20,
      detail: `Selected ${plugin.capability.label}`
    });
    const key = cacheKey(plugin.capability.id, cleanPrompt);
    const cached = this.cache.get(key);
    if (cached) {
      progress({ stage: "ready", percent: 100, detail: "Loaded validated artifact" });
      return { ok: true, artifact: cached };
    }
    progress({ stage: "preparing", percent: 42, detail: "Preparing deterministic data" });
    let artifact: WorkspaceArtifact | null;
    try {
      artifact = await plugin.build(cleanPrompt);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return errorResponse(`Renderer failed during data preparation: ${message}`);
    }
    if (!artifact) {
      return errorResponse(
        `${plugin.capability.label} could not build this request. Nothing was rendered.`
      );
    }
    if (signal?.aborted) return errorResponse("Rendering was cancelled.");
    progress({ stage: "rendering", percent: 70, detail: "Building interactive artifact" });
    progress({ stage: "validating", percent: 88, detail: "Validating renderer output" });
    const [valid, reason] = plugin.validate(artifact);
    if (!valid) {
      return errorResponse(
        `Renderer validation failed: ${reason || "unknown validation error"}`
      );
    }
    this.cache.put(key, artifact, plugin.estimateBytes(artifact));
    progress({ stage: "ready", percent: 100, detail: "Interactive artifact ready" });
    return { ok: true, artifact };
  }
}
