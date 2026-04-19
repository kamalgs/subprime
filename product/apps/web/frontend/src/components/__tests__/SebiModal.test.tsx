import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import SebiModal from "../SebiModal";

describe("SebiModal", () => {
  beforeEach(() => {
    // Clear cookies between tests
    document.cookie.split(";").forEach((c) => {
      const name = c.split("=")[0].trim();
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    });
  });

  it("is shown when no cookie is set", () => {
    render(<SebiModal />);
    expect(screen.getByText(/Before you continue/i)).toBeInTheDocument();
  });

  it("is hidden once the user acknowledges and cookie is set", () => {
    render(<SebiModal />);
    fireEvent.click(screen.getByRole("button", { name: /I understand/i }));
    expect(screen.queryByText(/Before you continue/i)).not.toBeInTheDocument();
    expect(document.cookie).toContain("sebi_ack=1");
  });

  it("is not shown when cookie already present", () => {
    document.cookie = "sebi_ack=1; path=/";
    render(<SebiModal />);
    expect(screen.queryByText(/Before you continue/i)).not.toBeInTheDocument();
  });
});
