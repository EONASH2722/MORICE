import { describe, expect, it } from "vitest";
import type {
  GraphArtifact,
  SimulationInstruction
} from "../src/contracts";
import {
  ArtifactCache,
  RendererManager,
  RendererRegistry,
  type RendererPlugin
} from "../src/renderer-manager";

function graphArtifact(): GraphArtifact {
  const instruction: SimulationInstruction = {
    simulationType: "graph",
    equations: ["x^2"],
    parameters: { deterministic: true }
  };
  return {
    id: "graph-1",
    title: "y=x^2",
    instruction,
    series: [
      {
        id: "series-1",
        label: "y=x^2",
        expression: "x^2",
        color: "#64d8ff",
        points: [
          { x: -1, y: 1 },
          { x: 0, y: 0 },
          { x: 1, y: 1 }
        ]
      }
    ],
    viewport: { xMin: -2, xMax: 2, yMin: -1, yMax: 4 }
  };
}

function graphPlugin(builds: { count: number }): RendererPlugin<GraphArtifact> {
  return {
    capability: {
      id: "math.graph",
      label: "Graph",
      interactive: true,
      dimensions: ["2d"]
    },
    canRender: (prompt) => prompt.includes("plot"),
    build: async () => {
      builds.count += 1;
      return graphArtifact();
    },
    validate: (artifact) => [
      artifact.series[0]?.points.length === 3,
      "expected three points"
    ],
    estimateBytes: () => 128
  };
}

describe("RendererManager", () => {
  it("validates and caches deterministic artifacts", async () => {
    const builds = { count: 0 };
    const registry = new RendererRegistry();
    registry.register(graphPlugin(builds));
    const manager = new RendererManager(registry, new ArtifactCache(1024 * 1024));
    const stages: string[] = [];

    const first = await manager.render("plot x^2", (progress) => {
      stages.push(progress.stage);
    });
    const second = await manager.render("plot x^2");

    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
    expect(builds.count).toBe(1);
    expect(stages).toContain("validating");
    expect(stages.at(-1)).toBe("ready");
  });

  it("fails honestly when no renderer supports the request", async () => {
    const manager = new RendererManager();
    const result = await manager.render("tell me a joke");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.message).toContain("Nothing was rendered");
  });
});
