import { describe, expect, it } from "vitest";
import { instructionFromPrompt } from "../src/coordinator";

describe("instructionFromPrompt", () => {
  it("extracts an ordinary graph deterministically", () => {
    const instruction = instructionFromPrompt("Plot y=x^2-4*x+3");

    expect(instruction?.simulationType).toBe("graph");
    expect(instruction?.equations).toEqual(["x^2-4*x+3"]);
    expect(instruction?.parameters.darkMode).toBe(true);
  });

  it("routes polar graphs", () => {
    const instruction = instructionFromPrompt("Plot polar r=2*cos(theta)");

    expect(instruction?.simulationType).toBe("polar-graph");
    expect(instruction?.equations).toEqual(["2*cos(theta)"]);
  });

  it("routes parametric graphs", () => {
    const instruction = instructionFromPrompt("Parametric x(t)=cos(t), y(t)=sin(t)");

    expect(instruction?.simulationType).toBe("parametric-graph");
    expect(instruction?.equations).toEqual(["x=cos(t)", "y=sin(t)"]);
  });

  it("caps particle requests at the renderer limit", () => {
    const instruction = instructionFromPrompt("Simulate 9000 particles with gravity");

    expect(instruction?.simulationType).toBe("particle-2d");
    expect(instruction?.parameters.particles).toBe(1600);
  });

  it("preserves commas inside piecewise expressions", () => {
    const instruction = instructionFromPrompt(
      "Plot y=piecewise(x<0, x^2, 2*x+1)"
    );

    expect(instruction?.equations).toEqual(["piecewise(x<0, x^2, 2*x+1)"]);
  });

  it("routes a real three-dimensional particle request", () => {
    const instruction = instructionFromPrompt(
      "Simulate 200 particles in a 3D box"
    );

    expect(instruction?.simulationType).toBe("particle-3d");
    expect(instruction?.parameters.views).toEqual(["2d", "3d"]);
  });

  it("fails closed for an unsupported SPH request", () => {
    expect(instructionFromPrompt("Simulate an SPH fluid tank")).toBeNull();
  });

  it("returns null for unsupported ordinary chat", () => {
    expect(instructionFromPrompt("Tell me a short joke")).toBeNull();
  });
});
