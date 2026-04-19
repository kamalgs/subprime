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
    expect(screen.getAllByText(/Plan|Profile|Strategy/).length).toBeGreaterThanOrEqual(4);
  });

  it("fills three pills (2 done + 1 current) at /step/3", () => {
    const { container } = renderAt("/step/3");
    // Pills: done + active both get bg-primary-600; upcoming do not.
    const filled = container.querySelectorAll(".bg-primary-600");
    expect(filled.length).toBe(3);
  });

  it("no pill filled at an unknown path", () => {
    const { container } = renderAt("/somewhere-else");
    expect(container.querySelectorAll(".bg-primary-600").length).toBe(0);
  });
});
