import type { SimulationInstruction } from "./contracts";

const GRAPH_MARKERS = ["plot", "graph", "curve", "function", "equation", "polar", "parametric"];
const PHYSICS_MARKERS = ["simulate", "physics", "particle", "projectile", "gravity", "collision", "rigid", "spring"];

function cleanPrompt(prompt: string): string {
  return prompt.trim().replace(/\s+/g, " ");
}

function isNonEmptyString(value: string | undefined): value is string {
  return typeof value === "string" && value.length > 0;
}

function extractEquations(prompt: string): readonly string[] {
  const matches = [...prompt.matchAll(/y\s*=\s*([^,;\n]+)/gi)]
    .map((match) => match[1]?.trim())
    .filter(isNonEmptyString);
  if (matches.length > 0) return matches;
  if (/\bx\b|\bsin\b|\bcos\b|\btan\b|\^/.test(prompt.toLowerCase())) {
    return [prompt.replace(/^(plot|graph|draw|show)\s+/i, "").trim()];
  }
  return [];
}

export function instructionFromPrompt(prompt: string): SimulationInstruction | null {
  const cleaned = cleanPrompt(prompt);
  const lowered = cleaned.toLowerCase();
  const graphIntent = GRAPH_MARKERS.some((marker) => lowered.includes(marker));
  const physicsIntent = PHYSICS_MARKERS.some((marker) => lowered.includes(marker));

  if (graphIntent) {
    const polarMatches = [...cleaned.matchAll(/\br\s*=\s*([^,;\n]+)/gi)]
      .map((match) => match[1]?.trim())
      .filter(isNonEmptyString);
    if (lowered.includes("polar") || polarMatches.length > 0) {
      return {
        simulationType: "polar-graph",
        equations: polarMatches.length > 0 ? polarMatches : [cleaned],
        parameters: {
          thetaMin: 0,
          thetaMax: Math.PI * 4,
          samples: 1000,
          darkMode: true
        }
      };
    }

    const xMatch = cleaned.match(/\bx\s*(?:\(t\))?\s*=\s*([^,;\n]+)/i);
    const yMatch = cleaned.match(/\by\s*(?:\(t\))?\s*=\s*([^,;\n]+)/i);
    if (lowered.includes("parametric") || (xMatch && yMatch)) {
      const xEquation = xMatch?.[1]?.trim();
      const yEquation = yMatch?.[1]?.trim();
      if (!xEquation || !yEquation) return null;
      return {
        simulationType: "parametric-graph",
        equations: [`x=${xEquation}`, `y=${yEquation}`],
        parameters: {
          tMin: 0,
          tMax: Math.PI * 2,
          samples: 1000,
          darkMode: true
        }
      };
    }

    const equations = extractEquations(cleaned);
    if (equations.length === 0) return null;
    return {
      simulationType: "graph",
      equations,
      parameters: {
        xMin: -10,
        xMax: 10,
        samples: 1000,
        darkMode: true
      }
    };
  }

  if (physicsIntent) {
    const particleMatch = lowered.match(/(\d{1,5})\s*(particles|balls|bodies)/);
    const particles = particleMatch?.[1] ? Number(particleMatch[1]) : lowered.includes("projectile") ? 1 : 120;
    return {
      simulationType: lowered.includes("projectile") ? "projectile-2d" : "particle-2d",
      equations: [],
      parameters: {
        particles: Math.min(Math.max(particles, 1), 1600),
        gravity: lowered.includes("zero gravity") ? 0 : 9.81,
        collisions: true,
        deterministic: true
      }
    };
  }

  return null;
}
