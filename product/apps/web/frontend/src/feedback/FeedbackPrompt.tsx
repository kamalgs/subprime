// FeedbackPrompt — modal NPS-style prompt shown once per session on the plan
// page. Triggers on (active dwell ≥ threshold) OR (scroll past target %),
// whichever fires first. Suppressed via sessionStorage after submit/skip.

import { useEffect, useRef, useState } from "react";
import { postFeedback } from "../api/client";

const STORAGE_KEY = "feedback_prompt_done";
// Cross-tab "show on next mount" flag (used when pagehide fires while the
// modal hasn't shown yet — best-effort intent capture).
const PENDING_KEY = "feedback_prompt_pending";

export interface FeedbackPromptProps {
  /** Render gate — when false, dwell/scroll listeners do not arm. */
  enabled?: boolean;
  /** Active dwell threshold in ms (default 30s). Lowered in tests. */
  dwellMs?: number;
  /** Scroll-depth threshold in pct (default 70). */
  scrollPct?: number;
}

type Actionable = "yes" | "mostly" | "no";

function readScrollPct(): number {
  const doc = document.documentElement;
  const scrollTop = window.scrollY || doc.scrollTop || 0;
  const viewport = window.innerHeight || doc.clientHeight || 0;
  const full = doc.scrollHeight || 0;
  if (full <= viewport) return 0; // can't scroll → never trigger via scroll
  return Math.min(100, Math.max(0, Math.round(((scrollTop + viewport) / full) * 100)));
}

export default function FeedbackPrompt({
  enabled = true,
  dwellMs = 30_000,
  scrollPct = 70,
}: FeedbackPromptProps) {
  const [shown, setShown] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [nps, setNps] = useState<number>(8);
  const [actionable, setActionable] = useState<Actionable | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  // Once we've shown or fired before, never re-arm in this mount.
  const triggeredRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    if (typeof window === "undefined") return;
    try {
      if (sessionStorage.getItem(STORAGE_KEY) === "1") {
        triggeredRef.current = true;
        return;
      }
      // pagehide-from-prior-mount intent → show immediately on next visit.
      if (sessionStorage.getItem(PENDING_KEY) === "1") {
        sessionStorage.removeItem(PENDING_KEY);
        triggeredRef.current = true;
        setShown(true);
        return;
      }
    } catch {
      // sessionStorage unavailable — fail open.
    }

    let activeStart: number | null = null;
    let unflushedActiveMs = 0;

    const trigger = () => {
      if (triggeredRef.current) return;
      triggeredRef.current = true;
      setShown(true);
    };

    const isActive = () =>
      document.visibilityState === "visible" && document.hasFocus();

    const tick = () => {
      const now = Date.now();
      const total = unflushedActiveMs + (activeStart ? now - activeStart : 0);
      if (total >= dwellMs) trigger();
    };

    const stamp = () => {
      const now = Date.now();
      const wantActive = isActive();
      if (wantActive && activeStart === null) {
        activeStart = now;
      } else if (!wantActive && activeStart !== null) {
        unflushedActiveMs += now - activeStart;
        activeStart = null;
      }
    };

    const onScroll = () => {
      if (readScrollPct() >= scrollPct) trigger();
    };

    const onPageHide = () => {
      if (triggeredRef.current) return;
      // Stash intent so it surfaces on the user's next visit.
      try {
        sessionStorage.setItem(PENDING_KEY, "1");
      } catch {
        // ignore
      }
    };

    stamp();
    const interval = window.setInterval(() => {
      stamp();
      tick();
    }, 1000);
    document.addEventListener("visibilitychange", stamp);
    window.addEventListener("focus", stamp);
    window.addEventListener("blur", stamp);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", onPageHide);
    onScroll();

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", stamp);
      window.removeEventListener("focus", stamp);
      window.removeEventListener("blur", stamp);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", onPageHide);
    };
  }, [enabled, dwellMs, scrollPct]);

  const markDone = () => {
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setSubmitted(true);
    setShown(false);
  };

  const skip = () => markDone();

  const submit = async () => {
    if (actionable === null) return;
    setBusy(true);
    const ok = await postFeedback({
      nps,
      actionable,
      free_text: text.trim() ? text.trim().slice(0, 500) : null,
    });
    setBusy(false);
    if (!ok) {
      // Opportunistic — don't block the user. Logging only.
      // eslint-disable-next-line no-console
      console.warn("feedback: server rejected the submission, treating as done");
    }
    markDone();
  };

  if (!shown || submitted) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="feedback-prompt-title"
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40 px-4 py-6"
    >
      <div className="card card-spacious w-full max-w-md space-y-4">
        <div className="flex items-start justify-between gap-3">
          <h3 id="feedback-prompt-title" className="text-lg font-semibold">
            Quick feedback?
          </h3>
          <button
            type="button"
            onClick={skip}
            className="text-xs text-gray-500 dark:text-slate-400 hover:text-primary-600"
            aria-label="Skip feedback"
          >
            Skip
          </button>
        </div>

        <div>
          <label className="text-sm font-medium" htmlFor="feedback-nps">
            How likely are you to recommend Benji?
          </label>
          <input
            id="feedback-nps"
            type="range"
            min={0}
            max={10}
            step={1}
            value={nps}
            onChange={(e) => setNps(Number(e.target.value))}
            className="w-full mt-2"
            aria-valuemin={0}
            aria-valuemax={10}
            aria-valuenow={nps}
          />
          <div className="flex justify-between text-xs text-gray-500 dark:text-slate-400 mt-1">
            <span>0 — Not at all</span>
            <span className="font-mono font-semibold text-primary-600 dark:text-primary-300">
              {nps}
            </span>
            <span>10 — Definitely</span>
          </div>
        </div>

        <fieldset>
          <legend className="text-sm font-medium">Was this actionable?</legend>
          <div className="grid grid-cols-3 gap-2 mt-2" role="radiogroup">
            {(
              [
                ["yes", "Yes"],
                ["mostly", "Mostly"],
                ["no", "Not really"],
              ] as Array<[Actionable, string]>
            ).map(([val, label]) => {
              const active = actionable === val;
              return (
                <button
                  key={val}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setActionable(val)}
                  className={
                    "text-sm px-3 py-2 rounded-lg border transition-colors " +
                    (active
                      ? "border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200"
                      : "border-gray-200 dark:border-slate-700 hover:border-primary-400")
                  }
                >
                  {label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label className="text-sm font-medium" htmlFor="feedback-free-text">
            Anything that would make this more useful? <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <textarea
            id="feedback-free-text"
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, 500))}
            rows={3}
            maxLength={500}
            className="input mt-2 w-full text-sm"
            placeholder="Optional"
          />
          <p className="text-xs text-gray-400 dark:text-slate-500 text-right mt-1">
            {text.length}/500
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={skip} className="btn btn-secondary text-sm">
            Skip
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || actionable === null}
            className="btn btn-primary text-sm disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}
