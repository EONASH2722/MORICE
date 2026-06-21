export type SimulationType =
  | "graph"
  | "parametric-graph"
  | "polar-graph"
  | "implicit-graph"
  | "particle-2d"
  | "projectile-2d"
  | "rigid-body-2d"
  | "particle-3d"
  | "rigid-body-3d"
  | "soft-body-3d";

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

export interface GraphArtifact {
  id: string;
  title: string;
  instruction: SimulationInstruction;
  series: readonly GraphSeries[];
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

export type WorkspaceArtifact = GraphArtifact | PhysicsArtifact;

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
