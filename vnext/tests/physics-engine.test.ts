import { describe, expect, it } from "vitest";
import type { SimulationInstruction } from "../src/contracts";
import {
  createPhysicsState,
  physicsSnapshot,
  stepPhysics,
  validatePhysicsState
} from "../src/physics-engine";

function instruction(type: "particle-2d" | "particle-3d"): SimulationInstruction {
  return {
    simulationType: type,
    equations: [],
    parameters: {
      particles: 32,
      gravity: 9.81,
      width: 320,
      height: 200,
      depth: 180,
      restitution: 1,
      deterministic: true
    }
  };
}

describe("deterministic physics engine", () => {
  it("creates identical state for identical instructions", () => {
    expect(createPhysicsState(instruction("particle-2d")).particles).toEqual(
      createPhysicsState(instruction("particle-2d")).particles
    );
  });

  it("keeps two-dimensional particles inside validated bounds", () => {
    const state = createPhysicsState(instruction("particle-2d"));
    for (let frame = 0; frame < 240; frame += 1) stepPhysics(state, 1 / 120);

    expect(validatePhysicsState(state)).toEqual([true, ""]);
    expect(physicsSnapshot(state).particles).toHaveLength(32);
  });

  it("preserves real depth state for a three-dimensional simulation", () => {
    const state = createPhysicsState(instruction("particle-3d"));
    stepPhysics(state, 1 / 30);
    const snapshot = physicsSnapshot(state);

    expect(state.dimensions).toBe(3);
    expect(
      snapshot.particles.every((particle) => particle.position.length === 3)
    ).toBe(true);
    expect(validatePhysicsState(state)).toEqual([true, ""]);
  });

  it("rejects unsupported physics instead of substituting particles", () => {
    expect(() =>
      createPhysicsState({
        simulationType: "soft-body-3d",
        equations: [],
        parameters: {}
      })
    ).toThrow("does not support");
  });
});
