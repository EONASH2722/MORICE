/**
 * VNext Science Workspace
 * TypeScript engine for graph rendering and physics simulations
 */

export { renderGraph, evaluateExpression, generateXValues, findCriticalPoints } from './graph-renderer';
export type { PlotlyGraphConfig } from './graph-renderer';
export { instructionFromPrompt } from './coordinator';
export {
  createPhysicsState,
  physicsSnapshot,
  stepPhysics,
  validatePhysicsState
} from "./physics-engine";
export type { PhysicsEngineState } from "./physics-engine";
export {
  ArtifactCache,
  RendererManager,
  RendererRegistry
} from "./renderer-manager";
export type {
  ProgressListener,
  RendererCapability,
  RendererPlugin
} from "./renderer-manager";
export type {
  SimulationInstruction,
  GraphArtifact,
  GraphSurface,
  PhysicsArtifact,
  MoleculeArtifact,
  DiagramArtifact
} from './contracts';
