import * as Plotly from "plotly.js-dist-min";
import { math } from "mathjs";
import type { GraphArtifact, SimulationInstruction } from "./contracts";

export interface PlotlyGraphConfig {
  container: string | HTMLElement;
  darkMode?: boolean;
  showGrid?: boolean;
  showLegend?: boolean;
  enableLatex?: boolean;
}

/**
 * Renders a GraphArtifact using Plotly with support for LaTeX notation in labels and titles.
 */
export async function renderGraph(artifact: GraphArtifact, config: PlotlyGraphConfig): Promise<void> {
  if (!artifact || !artifact.series || artifact.series.length === 0) {
    throw new Error("Invalid graph artifact: no series data");
  }

  const containerEl =
    typeof config.container === "string" ? document.getElementById(config.container) : config.container;

  if (!containerEl) {
    throw new Error(`Container not found: ${config.container}`);
  }

  // Build Plotly traces from series
  const traces = artifact.series.map((series) => ({
    x: series.points.map((p) => p.x),
    y: series.points.map((p) => p.y),
    mode: "lines+markers" as const,
    name: config.enableLatex ? `$${series.label}$` : series.label,
    line: {
      color: series.color,
      width: 2,
    },
    marker: {
      size: 4,
      opacity: 0.7,
    },
    hovertemplate: `<b>${series.label}</b><br>x: %{x:.4f}<br>y: %{y:.4f}<extra></extra>`,
  }));

  // Build layout with LaTeX support
  const layout: Partial<Plotly.Layout> = {
    title: {
      text: config.enableLatex ? `$${artifact.title}$` : artifact.title,
      font: {
        size: 18,
        color: config.darkMode ? "#e5e7eb" : "#1f2937",
      },
    },
    xaxis: {
      title: {
        text: config.enableLatex ? "$x$" : "x",
        font: {
          size: 14,
          color: config.darkMode ? "#d1d5db" : "#374151",
        },
      },
      range: [artifact.viewport.xMin, artifact.viewport.xMax],
      showgrid: config.showGrid !== false,
      gridwidth: 1,
      gridcolor: config.darkMode ? "#374151" : "#e5e7eb",
      zeroline: true,
      zerolinewidth: 2,
      zerolinecolor: config.darkMode ? "#4b5563" : "#d1d5db",
    },
    yaxis: {
      title: {
        text: config.enableLatex ? "$y$" : "y",
        font: {
          size: 14,
          color: config.darkMode ? "#d1d5db" : "#374151",
        },
      },
      range: [artifact.viewport.yMin, artifact.viewport.yMax],
      showgrid: config.showGrid !== false,
      gridwidth: 1,
      gridcolor: config.darkMode ? "#374151" : "#e5e7eb",
      zeroline: true,
      zerolinewidth: 2,
      zerolinecolor: config.darkMode ? "#4b5563" : "#d1d5db",
    },
    plot_bgcolor: config.darkMode ? "#1f2937" : "#ffffff",
    paper_bgcolor: config.darkMode ? "#111827" : "#f9fafb",
    font: {
      family: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      color: config.darkMode ? "#e5e7eb" : "#1f2937",
    },
    margin: {
      l: 60,
      r: 40,
      t: 60,
      b: 60,
    },
    hovermode: "closest" as const,
    showlegend: config.showLegend !== false,
    legend: {
      x: 0.02,
      y: 0.98,
      bgcolor: config.darkMode ? "rgba(17, 24, 39, 0.9)" : "rgba(255, 255, 255, 0.9)",
      bordercolor: config.darkMode ? "#4b5563" : "#e5e7eb",
      borderwidth: 1,
    },
  };

  const plotConfig: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["pan2d", "lasso2d", "select2d"],
    toImageButtonOptions: {
      format: "png" as const,
      filename: artifact.title.replace(/[^a-z0-9]/gi, "_").toLowerCase(),
      height: 800,
      width: 1200,
      scale: 2,
    },
  };

  // Use MathJax for LaTeX rendering if enabled
  if (config.enableLatex && typeof (window as any).MathJax !== "undefined") {
    layout.font = {
      ...layout.font,
      family: '"Computer Modern", serif',
    };
  }

  await Plotly.newPlot(containerEl, traces, layout as Plotly.Layout, plotConfig);
}

/**
 * Evaluates a mathematical expression at specific x values.
 * Returns points for plotting.
 */
export function evaluateExpression(
  expression: string,
  xValues: number[]
): { x: number; y: number }[] {
  const points: { x: number; y: number }[] = [];

  for (const x of xValues) {
    try {
      const compiled = math.compile(expression);
      const y = compiled.evaluate({ x });

      if (typeof y === "number" && isFinite(y)) {
        points.push({ x, y });
      }
    } catch (error) {
      // Skip invalid points
      continue;
    }
  }

  return points;
}

/**
 * Generate evenly spaced x values for plotting.
 */
export function generateXValues(xMin: number, xMax: number, samples: number = 1000): number[] {
  const step = (xMax - xMin) / samples;
  const values: number[] = [];

  for (let i = 0; i <= samples; i++) {
    values.push(xMin + i * step);
  }

  return values;
}

/**
 * Detect intercepts and extrema points in a dataset.
 */
export function findCriticalPoints(
  points: { x: number; y: number }[]
): {
  xIntercepts: { x: number; y: number }[];
  yIntercepts: { x: number; y: number }[];
  extrema: { x: number; y: number; type: "max" | "min" }[];
} {
  const xIntercepts: { x: number; y: number }[] = [];
  const yIntercepts: { x: number; y: number }[] = [];
  const extrema: { x: number; y: number; type: "max" | "min" }[] = [];

  // Find x-intercepts (where y ≈ 0)
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];

    // Zero crossing
    if ((p1.y < 0 && p2.y > 0) || (p1.y > 0 && p2.y < 0)) {
      const t = -p1.y / (p2.y - p1.y);
      const x = p1.x + t * (p2.x - p1.x);
      if (Math.abs(x) < 1e10) {
        xIntercepts.push({ x, y: 0 });
      }
    }
  }

  // Find y-intercept (where x ≈ 0)
  if (points.length > 0) {
    const closest = points.reduce((prev, curr) =>
      Math.abs(curr.x) < Math.abs(prev.x) ? curr : prev
    );
    if (Math.abs(closest.x) < 1) {
      yIntercepts.push(closest);
    }
  }

  // Find local extrema
  for (let i = 1; i < points.length - 1; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const next = points[i + 1];

    // Local maximum
    if (curr.y >= prev.y && curr.y >= next.y && Math.abs(curr.y) < 1e10) {
      extrema.push({ ...curr, type: "max" });
    }

    // Local minimum
    if (curr.y <= prev.y && curr.y <= next.y && Math.abs(curr.y) < 1e10) {
      extrema.push({ ...curr, type: "min" });
    }
  }

  return { xIntercepts, yIntercepts, extrema };
}
