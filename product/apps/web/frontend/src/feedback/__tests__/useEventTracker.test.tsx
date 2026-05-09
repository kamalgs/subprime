import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useEventTracker } from "../useEventTracker";

function lastFetchBody(fetchMock: ReturnType<typeof vi.fn>, url: string): any | null {
  for (let i = fetchMock.mock.calls.length - 1; i >= 0; i--) {
    const [u, init] = fetchMock.mock.calls[i];
    if (typeof u === "string" && u.includes(url)) {
      return JSON.parse((init as RequestInit).body as string);
    }
  }
  return null;
}

describe("useEventTracker", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    // sendBeacon is null in jsdom — let API client fall through to fetch.
    Object.defineProperty(navigator, "sendBeacon", {
      value: undefined,
      configurable: true,
    });
    // Default: tab is visible + focused so dwell accrues.
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
  });

  it("flushes on the 5s interval and includes dwell seconds", async () => {
    const { unmount } = renderHook(() => useEventTracker("plan"));
    // Advance 6s so dwell crosses an integer second boundary.
    await act(async () => {
      vi.advanceTimersByTime(6000);
    });
    const body = lastFetchBody(fetchMock, "/api/v2/events");
    expect(body).not.toBeNull();
    const events = body.events as any[];
    const dwell = events.find((e) => e.kind === "dwell");
    expect(dwell).toBeDefined();
    expect(dwell.payload.page).toBe("plan");
    expect(dwell.payload.seconds).toBeGreaterThanOrEqual(5);
    unmount();
  });

  it("captures clicks on elements with data-track-as ancestors", async () => {
    const { unmount } = renderHook(() => useEventTracker("plan"));
    const wrapper = document.createElement("div");
    wrapper.setAttribute("data-track-as", "section_header");
    const inner = document.createElement("span");
    wrapper.appendChild(inner);
    document.body.appendChild(wrapper);

    inner.dispatchEvent(new MouseEvent("click", { bubbles: true }));

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    const body = lastFetchBody(fetchMock, "/api/v2/events");
    const click = body.events.find((e: any) => e.kind === "click");
    expect(click).toBeDefined();
    expect(click.payload.element).toBe("section_header");
    document.body.removeChild(wrapper);
    unmount();
  });

  it("ignores dwell while document is hidden", async () => {
    const { unmount } = renderHook(() => useEventTracker("plan"));
    // Hide the tab.
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    const body = lastFetchBody(fetchMock, "/api/v2/events");
    if (body) {
      // No dwell should accrue while hidden.
      const dwell = body.events.find((e: any) => e.kind === "dwell");
      expect(dwell?.payload?.seconds ?? 0).toBeLessThanOrEqual(1);
    }
    unmount();
  });

  it("emits final exit event on unmount", async () => {
    const { unmount } = renderHook(() => useEventTracker("plan"));
    fetchMock.mockClear();
    unmount();
    // After unmount, drained events flushed via fetch.
    await act(async () => {
      await Promise.resolve();
    });
    const body = lastFetchBody(fetchMock, "/api/v2/events");
    expect(body).not.toBeNull();
    const exit = body.events.find((e: any) => e.kind === "exit");
    expect(exit).toBeDefined();
    expect(exit.payload.nav_kind).toBe("internal");
  });

  it("swallows network failures silently", async () => {
    fetchMock.mockRejectedValue(new Error("network down"));
    const { unmount } = renderHook(() => useEventTracker("plan"));
    await act(async () => {
      vi.advanceTimersByTime(6000);
    });
    // No throw, no rejection — that's the contract.
    expect(true).toBe(true);
    unmount();
  });
});
