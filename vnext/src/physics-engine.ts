import type {
  ParticleState,
  PhysicsArtifact,
  SimulationInstruction
} from "./contracts";

interface MutableParticle {
  id: string;
  position: [number, number, number];
  velocity: [number, number, number];
  radius: number;
  mass: number;
}

export interface PhysicsEngineState {
  readonly instruction: SimulationInstruction;
  readonly dimensions: 2 | 3;
  readonly bounds: readonly [number, number, number];
  readonly gravity: number;
  readonly restitution: number;
  readonly fixedStepSeconds: number;
  elapsedSeconds: number;
  collisionCount: number;
  particles: MutableParticle[];
}

function numberParameter(
  instruction: SimulationInstruction,
  name: string,
  fallback: number
): number {
  const value = instruction.parameters[name];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function seededRandom(seedText: string): () => number {
  let state = 2166136261;
  for (const character of seedText) {
    state ^= character.charCodeAt(0);
    state = Math.imul(state, 16777619);
  }
  return () => {
    state += 0x6d2b79f5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

export function createPhysicsState(
  instruction: SimulationInstruction
): PhysicsEngineState {
  if (
    instruction.simulationType !== "particle-2d" &&
    instruction.simulationType !== "particle-3d"
  ) {
    throw new Error(
      `The deterministic particle engine does not support ${instruction.simulationType}.`
    );
  }
  const dimensions = instruction.simulationType === "particle-3d" ? 3 : 2;
  const count = Math.round(
    clamp(numberParameter(instruction, "particles", 120), 1, 1600)
  );
  const width = clamp(numberParameter(instruction, "width", 640), 100, 4096);
  const height = clamp(numberParameter(instruction, "height", 380), 100, 4096);
  const depth = dimensions === 3
    ? clamp(numberParameter(instruction, "depth", 380), 100, 4096)
    : 1;
  const random = seededRandom(JSON.stringify(instruction));
  const particles: MutableParticle[] = [];
  for (let index = 0; index < count; index += 1) {
    const radius = 2.5 + random() * 3.5;
    const mass = Math.max(0.5, radius / 3);
    particles.push({
      id: `particle-${index}`,
      position: [
        radius + random() * (width - radius * 2),
        radius + random() * (height - radius * 2),
        dimensions === 3
          ? radius + random() * (depth - radius * 2)
          : 0
      ],
      velocity: [
        (random() - 0.5) * 130,
        (random() - 0.5) * 100,
        dimensions === 3 ? (random() - 0.5) * 130 : 0
      ],
      radius,
      mass
    });
  }
  return {
    instruction,
    dimensions,
    bounds: [width, height, depth],
    gravity: numberParameter(instruction, "gravity", 9.81),
    restitution: clamp(numberParameter(instruction, "restitution", 0.96), 0, 1),
    fixedStepSeconds: 1 / 120,
    elapsedSeconds: 0,
    collisionCount: 0,
    particles
  };
}

function resolveBounds(state: PhysicsEngineState, particle: MutableParticle): void {
  for (let axis = 0; axis < state.dimensions; axis += 1) {
    const minimum = particle.radius;
    const maximum = state.bounds[axis]! - particle.radius;
    if (particle.position[axis]! < minimum) {
      particle.position[axis] = minimum;
      particle.velocity[axis] = Math.abs(particle.velocity[axis]!) * state.restitution;
      state.collisionCount += 1;
    } else if (particle.position[axis]! > maximum) {
      particle.position[axis] = maximum;
      particle.velocity[axis] = -Math.abs(particle.velocity[axis]!) * state.restitution;
      state.collisionCount += 1;
    }
  }
}

function resolveParticlePair(
  state: PhysicsEngineState,
  first: MutableParticle,
  second: MutableParticle
): void {
  const delta: [number, number, number] = [
    second.position[0] - first.position[0],
    second.position[1] - first.position[1],
    second.position[2] - first.position[2]
  ];
  const distanceSquared = delta
    .slice(0, state.dimensions)
    .reduce((sum, value) => sum + value * value, 0);
  const minimumDistance = first.radius + second.radius;
  if (distanceSquared <= 1e-12 || distanceSquared >= minimumDistance ** 2) return;
  const distance = Math.sqrt(distanceSquared);
  const normal = delta.map((value) => value / distance) as [number, number, number];
  const relativeVelocity = normal
    .slice(0, state.dimensions)
    .reduce(
      (sum, value, axis) =>
        sum + (second.velocity[axis]! - first.velocity[axis]!) * value,
      0
    );
  const overlap = minimumDistance - distance;
  const totalMass = first.mass + second.mass;
  for (let axis = 0; axis < state.dimensions; axis += 1) {
    first.position[axis] =
      first.position[axis]! -
      normal[axis]! * overlap * (second.mass / totalMass);
    second.position[axis] =
      second.position[axis]! +
      normal[axis]! * overlap * (first.mass / totalMass);
  }
  if (relativeVelocity >= 0) return;
  const impulse =
    (-(1 + state.restitution) * relativeVelocity) /
    (1 / first.mass + 1 / second.mass);
  for (let axis = 0; axis < state.dimensions; axis += 1) {
    first.velocity[axis] =
      first.velocity[axis]! - (impulse * normal[axis]!) / first.mass;
    second.velocity[axis] =
      second.velocity[axis]! + (impulse * normal[axis]!) / second.mass;
  }
  state.collisionCount += 1;
}

export function stepPhysics(
  state: PhysicsEngineState,
  elapsedSeconds: number
): void {
  if (!Number.isFinite(elapsedSeconds) || elapsedSeconds < 0) {
    throw new Error("Physics elapsed time must be a finite non-negative number.");
  }
  let remaining = Math.min(elapsedSeconds, 0.25);
  while (remaining > 1e-12) {
    const step = Math.min(state.fixedStepSeconds, remaining);
    for (const particle of state.particles) {
      particle.velocity[1] = particle.velocity[1] + state.gravity * step;
      for (let axis = 0; axis < state.dimensions; axis += 1) {
        particle.position[axis] =
          particle.position[axis]! + particle.velocity[axis]! * step;
      }
      resolveBounds(state, particle);
    }
    for (let first = 0; first < state.particles.length; first += 1) {
      for (let second = first + 1; second < state.particles.length; second += 1) {
        resolveParticlePair(
          state,
          state.particles[first]!,
          state.particles[second]!
        );
      }
    }
    state.elapsedSeconds += step;
    remaining -= step;
  }
}

export function validatePhysicsState(
  state: PhysicsEngineState
): readonly [boolean, string] {
  if (state.particles.length < 1 || state.particles.length > 1600) {
    return [false, "particle count is outside the validated range"];
  }
  for (const particle of state.particles) {
    for (let axis = 0; axis < state.dimensions; axis += 1) {
      const value = particle.position[axis]!;
      if (!Number.isFinite(value)) return [false, "particle position is not finite"];
      if (value < particle.radius - 1e-6) return [false, "particle escaped lower bound"];
      if (value > state.bounds[axis]! - particle.radius + 1e-6) {
        return [false, "particle escaped upper bound"];
      }
    }
  }
  return [true, ""];
}

export function physicsSnapshot(state: PhysicsEngineState): PhysicsArtifact {
  const particles: ParticleState[] = state.particles.map((particle) => ({
    id: particle.id,
    position: state.dimensions === 3
      ? [...particle.position]
      : [particle.position[0], particle.position[1]],
    velocity: state.dimensions === 3
      ? [...particle.velocity]
      : [particle.velocity[0], particle.velocity[1]],
    radius: particle.radius,
    mass: particle.mass
  }));
  return {
    id: `physics-${state.elapsedSeconds.toFixed(6)}`,
    title: `${state.particles.length}-particle simulation`,
    instruction: state.instruction,
    particles,
    stats: {
      fps: 120,
      particles: particles.length,
      collisionsPerSecond:
        state.elapsedSeconds > 0
          ? state.collisionCount / state.elapsedSeconds
          : 0
    }
  };
}
