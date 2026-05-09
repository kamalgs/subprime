// useEventTracker — batches UX events for /api/v2/events.
//
// Tracks scroll depth, clicks (via `data-track-as` ancestor lookup), active
// dwell (visible AND focused), and best-effort exit intent. Flushes every
// 5s while active, on unmount, and on `pagehide` (via sendBeacon for
// reliability when the tab is going away). Best-effort: 503 / network
// failures are swallowed by the API client.

import { useEffect, useRef } from "react";
import { postEvents, sendEventsBeacon, type TrackEvent } from "../api/client";

const FLUSH_INTERVAL_MS = 5000;

type ExitKind = "back" | "close" | "forward" | "internal";

interface TrackerState {
  pageKey: string;
  buffer: TrackEvent[];
  maxScrollPct: number;
  // Active dwell accounting (page is visible AND tab is focused)
  active: boolean;
  activeStartedAt: number | null;
  unflushedActiveMs: number;
  exitIntent: ExitKind | null;
}

function readScrollPct(): number {
  // Use documentElement; clamp to [0, 100]. If page isn't scrollable, count as 100.
  const doc = document.documentElement;
  const scrollTop = window.scrollY || doc.scrollTop || 0;
  const viewport = window.innerHeight || doc.clientHeight || 0;
  const full = doc.scrollHeight || 0;
  const scrollable = Math.max(full - viewport, 0);
  if (scrollable <= 0) return 100;
  return Math.min(100, Math.max(0, Math.round(((scrollTop + viewport) / full) * 100)));
}

function findTrackTarget(target: EventTarget | null): string | null {
  if (!target || !(target instanceof Element)) return null;
  const el = target.closest<HTMLElement>("[data-track-as]");
  return el?.dataset?.trackAs ?? null;
}

/**
 * Subscribe page-level event tracking for the current route.
 *
 * @param pageKey logical page identifier sent as part of every event payload
 *                (e.g. "plan", "strategy"). The hook also stamps it on the
 *                `kind` so server-side filtering is straightforward.
 */
export function useEventTracker(pageKey: string): void {
  // Stash state in a ref so listeners always see the latest values without
  // re-subscribing on every render.
  const stateRef = useRef<TrackerState>({
    pageKey,
    buffer: [],
    maxScrollPct: 0,
    active: false,
    activeStartedAt: null,
    unflushedActiveMs: 0,
    exitIntent: null,
  });

  useEffect(() => {
    const s = stateRef.current;
    s.pageKey = pageKey;

    const stampActiveStart = () => {
      const visible = document.visibilityState === "visible";
      const focused = document.hasFocus();
      const shouldBeActive = visible && focused;
      const now = Date.now();
      if (shouldBeActive && !s.active) {
        s.active = true;
        s.activeStartedAt = now;
      } else if (!shouldBeActive && s.active) {
        if (s.activeStartedAt !== null) {
          s.unflushedActiveMs += now - s.activeStartedAt;
        }
        s.active = false;
        s.activeStartedAt = null;
      }
    };

    const drainActiveMs = (): number => {
      if (s.active && s.activeStartedAt !== null) {
        const now = Date.now();
        s.unflushedActiveMs += now - s.activeStartedAt;
        s.activeStartedAt = now;
      }
      const ms = s.unflushedActiveMs;
      s.unflushedActiveMs = 0;
      return ms;
    };

    const buildFlushBatch = (includeExit: boolean): TrackEvent[] => {
      const out: TrackEvent[] = s.buffer.splice(0, s.buffer.length);
      const dwellMs = drainActiveMs();
      const dwellSec = Math.round(dwellMs / 1000);
      if (dwellSec > 0) {
        out.push({ kind: "dwell", payload: { page: s.pageKey, seconds: dwellSec } });
      }
      if (s.maxScrollPct > 0) {
        out.push({
          kind: "scroll_depth",
          payload: { page: s.pageKey, max_pct: s.maxScrollPct },
        });
        s.maxScrollPct = 0;
      }
      if (includeExit && s.exitIntent) {
        out.push({ kind: "exit", payload: { page: s.pageKey, nav_kind: s.exitIntent } });
        s.exitIntent = null;
      }
      // Cap to 50 — the backend rejects larger batches with 422. Drop the
      // oldest in the unlikely case we overflow.
      return out.slice(-50);
    };

    const flush = () => {
      const batch = buildFlushBatch(false);
      if (batch.length > 0) postEvents(batch);
    };

    const onScroll = () => {
      const pct = readScrollPct();
      if (pct > s.maxScrollPct) s.maxScrollPct = pct;
    };

    const onClick = (ev: MouseEvent) => {
      const element = findTrackTarget(ev.target);
      if (!element) return;
      s.buffer.push({ kind: "click", payload: { page: s.pageKey, element } });
    };

    const onVisibility = () => stampActiveStart();
    const onFocus = () => stampActiveStart();
    const onBlur = () => stampActiveStart();

    const onPopState = () => {
      s.exitIntent = "back";
    };
    const onPageHide = () => {
      const batch = buildFlushBatch(true);
      if (batch.length > 0) sendEventsBeacon(batch);
    };

    // Capture-phase click delegation so we never miss bubbled-and-stopped events.
    document.addEventListener("click", onClick, true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("blur", onBlur);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("popstate", onPopState);
    window.addEventListener("pagehide", onPageHide);

    // Initial scroll snapshot + activity stamp.
    onScroll();
    stampActiveStart();

    const interval = window.setInterval(flush, FLUSH_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("click", onClick, true);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("pagehide", onPageHide);
      // Final flush — internal navigation away from the page, so stamp
      // exit=internal when we have no other intent on file.
      if (!s.exitIntent) s.exitIntent = "internal";
      const batch = buildFlushBatch(true);
      if (batch.length > 0) postEvents(batch);
    };
    // We deliberately do NOT depend on pageKey here — re-subscribing on
    // every render would lose buffered state. Updating the key is handled
    // via the ref assignment at the top of the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageKey]);
}

export const __TEST_ONLY__ = { readScrollPct, findTrackTarget };
