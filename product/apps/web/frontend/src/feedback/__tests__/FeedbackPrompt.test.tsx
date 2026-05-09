import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import FeedbackPrompt from "../FeedbackPrompt";

describe("FeedbackPrompt", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    sessionStorage.clear();
    vi.useFakeTimers();
    fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    vi.spyOn(document, "hasFocus").mockReturnValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
  });

  it("does not render before any trigger fires", () => {
    render(<FeedbackPrompt dwellMs={30_000} />);
    expect(screen.queryByText(/Quick feedback/i)).not.toBeInTheDocument();
  });

  it("appears after the dwell threshold and submits feedback", async () => {
    render(<FeedbackPrompt dwellMs={2000} />);
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByText(/Quick feedback/i)).toBeInTheDocument();

    // Submit disabled until "actionable" picked.
    const sendBtn = screen.getByRole("button", { name: /^Send$/i });
    expect(sendBtn).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: /^Yes$/i }));
    expect(sendBtn).not.toBeDisabled();

    fireEvent.click(sendBtn);
    // Flush the awaits inside submit() under fake timers.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fetchMock).toHaveBeenCalled();
    const call = fetchMock.mock.calls.find(
      ([u]) => typeof u === "string" && u.includes("/api/v2/feedback"),
    );
    expect(call).toBeDefined();
    const body = JSON.parse((call![1] as RequestInit).body as string);
    expect(body.actionable).toBe("yes");
    expect(body.nps).toBeGreaterThanOrEqual(0);
    expect(body.nps).toBeLessThanOrEqual(10);
    // Suppressed after submit.
    expect(screen.queryByText(/Quick feedback/i)).not.toBeInTheDocument();
    expect(sessionStorage.getItem("feedback_prompt_done")).toBe("1");
  });

  it("dismisses on skip and stores the suppression flag", async () => {
    render(<FeedbackPrompt dwellMs={1000} />);
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    fireEvent.click(screen.getAllByRole("button", { name: /Skip/i })[0]);
    expect(screen.queryByText(/Quick feedback/i)).not.toBeInTheDocument();
    expect(sessionStorage.getItem("feedback_prompt_done")).toBe("1");
  });

  it("does not show when suppression flag is already set", async () => {
    sessionStorage.setItem("feedback_prompt_done", "1");
    render(<FeedbackPrompt dwellMs={500} />);
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.queryByText(/Quick feedback/i)).not.toBeInTheDocument();
  });

  it("shows immediately when pending flag is set from prior pagehide", () => {
    sessionStorage.setItem("feedback_prompt_pending", "1");
    render(<FeedbackPrompt dwellMs={30_000} />);
    expect(screen.getByText(/Quick feedback/i)).toBeInTheDocument();
    expect(sessionStorage.getItem("feedback_prompt_pending")).toBeNull();
  });

  it("treats server 503 as completed (no user-visible error)", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 503 }));
    render(<FeedbackPrompt dwellMs={500} />);
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    fireEvent.click(screen.getByRole("radio", { name: /^Mostly$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Send$/i }));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.queryByText(/Quick feedback/i)).not.toBeInTheDocument();
    expect(sessionStorage.getItem("feedback_prompt_done")).toBe("1");
  });
});
