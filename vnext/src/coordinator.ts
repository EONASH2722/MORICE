import type { SimulationInstruction } from "./contracts";

const GRAPH_MARKERS = ["plot", "graph", "curve", "function", "equation", "polar", "parametric"];
const PHYSICS_MARKERS = [
  "simulate",
  "physics",
  "particle",
  "projectile",
  "gravity",
  "collision",
  "spring",
  "pendulum",
  "wave",
  "ripple",
  "orbit",
  "circular motion"
];

function cleanPrompt(prompt: string): string {
  return prompt.trim().replace(/\s+/g, " ");
}

function isNonEmptyString(value: string | undefined): value is string {
  return typeof value === "string" && value.length > 0;
}

function splitTopLevelExpressions(source: string): readonly string[] {
  const expressions: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === "(" || character === "[" || character === "{") depth += 1;
    if (character === ")" || character === "]" || character === "}") {
      depth = Math.max(0, depth - 1);
    }
    if ((character === "," || character === ";" || character === "\n") && depth === 0) {
      const expression = source.slice(start, index).trim();
      if (expression) expressions.push(expression);
      start = index + 1;
    }
  }
  const finalExpression = source.slice(start).trim();
  if (finalExpression) expressions.push(finalExpression);
  return expressions;
}

function extractAssignedExpressions(prompt: string, variable: string): readonly string[] {
  const marker = new RegExp(`\\b${variable}\\s*=`, "gi");
  const starts = [...prompt.matchAll(marker)];
  return starts
    .map((match, index) => {
      const valueStart = (match.index ?? 0) + match[0].length;
      const valueEnd = starts[index + 1]?.index ?? prompt.length;
      return splitTopLevelExpressions(prompt.slice(valueStart, valueEnd))[0]?.trim();
    })
    .filter(isNonEmptyString);
}

function extractEquations(prompt: string): readonly string[] {
  const matches = extractAssignedExpressions(prompt, "y");
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
    if (/\b(?:fluid|sph|soft body|rigid body|double pendulum)\b/.test(lowered)) {
      return null;
    }
    const particleMatch = lowered.match(/(\d{1,5})\s*(particles|balls|bodies)/);
    const particles = particleMatch?.[1]
      ? Number(particleMatch[1])
      : lowered.includes("projectile") || lowered.includes("pendulum")
        ? 1
        : 120;
    const is3d = /\b3d\b|three-dimensional/.test(lowered);
    const simulationType = lowered.includes("projectile")
      ? "projectile-2d"
      : lowered.includes("pendulum")
        ? "pendulum-2d"
        : lowered.includes("wave") || lowered.includes("ripple")
          ? "wave-2d"
          : lowered.includes("circular motion")
            ? "circular-motion-2d"
            : is3d
              ? "particle-3d"
              : "particle-2d";
    return {
      simulationType,
      equations: [],
      parameters: {
        particles: Math.min(Math.max(particles, 1), 1600),
        gravity: lowered.includes("zero gravity") ? 0 : 9.81,
        collisions: true,
        deterministic: true,
        views: is3d ? ["2d", "3d"] : ["2d"]
      }
    };
  }

  return null;
}
