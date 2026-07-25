export type SimulationType =
  | "graph"
  | "parametric-graph"
  | "polar-graph"
  | "implicit-graph"
  | "surface-3d"
  | "particle-2d"
  | "projectile-2d"
  | "pendulum-2d"
  | "wave-2d"
  | "circular-motion-2d"
  | "rigid-body-2d"
  | "particle-3d"
  | "rigid-body-3d"
  | "soft-body-3d"
  | "molecule"
  | "diagram";

export type ScalarParameter = string | number | boolean;

export interface SimulationInstruction {
  simulationType: SimulationType;
  equations: readonly string[];
  parameters: Readonly<Record<string, ScalarParameter | readonly ScalarParameter[]>>;
}

export interface GraphPoint {
  x: number;
  y: number;
  label?: string;
}

export interface GraphSeries {
  id: string;
  label: string;
  expression: string;
  color: string;
  points: readonly GraphPoint[];
}

export interface GraphSurface {
  label: string;
  expression: string;
  x: readonly number[];
  y: readonly number[];
  z: readonly (readonly number[])[];
  zRange: readonly [number, number];
}

export interface GraphArtifact {
  id: string;
  title: string;
  instruction: SimulationInstruction;
  series: readonly GraphSeries[];
  surface?: GraphSurface;
  viewport: {
    xMin: number;
    xMax: number;
    yMin: number;
    yMax: number;
  };
}

export interface ParticleState {
  id: string;
  position: readonly [number, number, number?];
  velocity: readonly [number, number, number?];
  radius: number;
  mass: number;
}

export interface PhysicsArtifact {
  id: string;
  title: string;
  instruction: SimulationInstruction;
  particles: readonly ParticleState[];
  stats: {
    fps: number;
    particles: number;
    collisionsPerSecond: number;
  };
}

export interface MoleculeAtom {
  id: number;
  element: string;
  position: readonly [number, number, number];
  formalCharge: number;
}

export interface MoleculeBond {
  first: number;
  second: number;
  order: 1 | 2 | 3;
}

export interface MoleculeArtifact {
  id: string;
  title: string;
  instruction: SimulationInstruction;
  formula: string;
  molecularGeometry: string;
  electronGeometry: string;
  atoms: readonly MoleculeAtom[];
  bonds: readonly MoleculeBond[];
}

export interface DiagramNode {
  id: string;
  label: string;
}

export interface DiagramEdge {
  source: string;
  target: string;
  label?: string;
}

export interface DiagramArtifact {
  id: string;
  title: string;
  instruction: SimulationInstruction;
  nodes: readonly DiagramNode[];
  edges: readonly DiagramEdge[];
}

export type WorkspaceArtifact =
  | GraphArtifact
  | PhysicsArtifact
  | MoleculeArtifact
  | DiagramArtifact;

export interface EngineResult<TArtifact extends WorkspaceArtifact> {
  ok: true;
  artifact: TArtifact;
}

export interface EngineError {
  ok: false;
  message: string;
  recoverable: boolean;
}

export type EngineResponse<TArtifact extends WorkspaceArtifact> = EngineResult<TArtifact> | EngineError;
