/**
 * VNext Science Workspace
 * TypeScript engine for graph rendering and physics simulations
 */

export { renderGraph, evaluateExpression, generateXValues, findCriticalPoints } from './graph-renderer';
export type { PlotlyGraphConfig } from './graph-renderer';
export { instructionFromPrompt } from './coordinator';
export type { SimulationInstruction, GraphArtifact, PhysicsArtifact } from './contracts';
