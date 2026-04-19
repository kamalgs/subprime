import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import StepIndicator from "../StepIndicator";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <StepIndicator />
    </MemoryRouter>,
  );
}

describe("StepIndicator", () => {
  it("renders all four step labels", () => {
    renderAt("/step/2");
    // StepIndicator uses STEPS = ["Plan", "Profile", "Strategy", "Plan"]
    const labels = screen.getAllByText(/Plan|Profile|Strategy/);
    expect(labels.length).toBeGreaterThanOrEqual(4);
  });

  it("marks step 3 as active when path is /step/3", () => {
    const { container } = renderAt("/step/3");
    // Active step has the filled primary background
    const pills = container.querySelectorAll(".bg-primary-600");
    // Three pills are filled (steps 1 & 2 done with ✓, step 3 current)
    expect(pills.length).toBe(3);
  });

  it("marks no step as active at an unknown path", () => {
    const { container } = renderAt("/somewhere-else");
    const pills = container.querySelectorAll(".bg-primary-600");
    expect(pills.length).toBe(0);
  });
});
