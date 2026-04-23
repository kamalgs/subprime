import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getPlan } from "../api/client";
import type { Plan, PlanStatus, InvestorProfile } from "../api/types";
import CorpusChart from "../components/CorpusChart";
import PlanRevealModal from "../components/PlanRevealModal";
import Prose from "../components/Prose";

const ALL_STAGES = ["core", "risks", "setup"] as const;

const WISDOMS = [
  "Wealth, to those who wait, it comes.",
  "Consistency, beat genius it does.",
  "A molehill today. A mountain tomorrow. Compound, it must.",
  "Lead the horse to water, you can. Drink for him, you cannot.",
  "Time in the market, beat timing the market it does.",
  "Slow, the tortoise is. Finish the race, still he does.",
  "Greedy when fearful, be. Fearful when greedy, be.",
];

function fmtInr(v: number): string {
  if (!v) return "\u20B90";
  if (v >= 1e7) return `\u20B9${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `\u20B9${(v / 1e5).toFixed(2)} L`;
  return "\u20B9" + Math.round(v).toLocaleString("en-IN");
}

export default function Step4Plan() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<PlanStatus | null>(null);

  useEffect(() => {
    const src = new EventSource("/api/v2/plan/stream");
    src.addEventListener("stage", (e) => {
      setStatus(JSON.parse((e as MessageEvent).data));
    });
    src.addEventListener("done", () => src.close());
    src.onerror = () => src.close();
    return () => src.close();
  }, []);

  const stagesKey = (status?.stages_done || []).join(",");

  const plan = useQuery({
    queryKey: ["plan"],
    queryFn: getPlan,
    enabled: status?.ready === true,
  });

  // New stage landed → refetch the plan so newly-populated sections render.
  // Keep the query key stable so plan.data persists during refetch and
  // PlanView stays mounted (otherwise the disclaimer modal re-shows).
  useEffect(() => {
    if (stagesKey) qc.invalidateQueries({ queryKey: ["plan"] });
  }, [stagesKey, qc]);

  if (status?.error && !status.ready) {
    return (
      <div className="card card-spacious max-w-md mx-auto text-center space-y-4 mt-8">
        <h2 className="text-lg font-semibold">Plan generation failed</h2>
        <p className="text-sm text-gray-500 dark:text-slate-400">{status.error}</p>
        <Link to="/step/3" className="btn btn-primary">Back to strategy</Link>
      </div>
    );
  }

  if (!status?.ready || !plan.data) {
    const wisdom = WISDOMS[Math.floor(Date.now() / 6000) % WISDOMS.length];
    return (
      <div className="card card-spacious max-w-md mx-auto text-center space-y-5 mt-8">
        <div className="w-12 h-12 border-4 border-primary-200 dark:border-slate-700 border-t-primary-600 rounded-full animate-spin mx-auto" />
        <div>
          <h2 className="text-lg font-semibold">Building your plan</h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-slate-400">
            Selecting funds and computing projections…
          </p>
        </div>
        <div>
          <p className="text-sm italic text-primary-700 dark:text-primary-300">&ldquo;{wisdom}&rdquo;</p>
          <p className="text-xs text-gray-400 dark:text-slate-500 mt-1">— Benji</p>
        </div>
        <p className="text-xs text-gray-400 dark:text-slate-500">This usually takes 30–60 seconds.</p>
      </div>
    );
  }

  const done = new Set(status?.stages_done || []);
  const pending = ALL_STAGES.filter((s) => !done.has(s));

  return (
    <PlanView
      plan={plan.data.plan}
      profile={plan.data.profile}
      pendingStages={pending}
    />
  );
}

function SectionSkeleton({ title }: { title: string }) {
  return (
    <div className="card card-spacious">
      <h3 className="section-title flex items-center gap-2">
        {title}
        <span className="inline-block w-3 h-3 rounded-full bg-primary-300 dark:bg-primary-500 animate-pulse" />
      </h3>
      <div className="space-y-2">
        <div className="h-3 rounded bg-gray-200 dark:bg-slate-700 animate-pulse w-5/6" />
        <div className="h-3 rounded bg-gray-200 dark:bg-slate-700 animate-pulse w-4/6" />
        <div className="h-3 rounded bg-gray-200 dark:bg-slate-700 animate-pulse w-3/6" />
      </div>
    </div>
  );
}

function PlanView({
  plan,
  profile,
  pendingStages,
}: {
  plan: Plan;
  profile: InvestorProfile;
  pendingStages: readonly string[];
}) {
  const risksPending = pendingStages.includes("risks");
  const setupPending = pendingStages.includes("setup");
  const allStagesDone = pendingStages.length === 0;
  // Reveal gate resets on every mount — no sessionStorage, no cookie.
  // Users see the disclaimer each time they land on the plan screen.
  const [revealed, setRevealed] = useState(false);
  const totalSip = plan.allocations.reduce((a, x) => a + (x.monthly_sip_inr ?? 0), 0);
  const houses = new Set(plan.allocations.map((a) => a.fund.fund_house).filter(Boolean));
  const pr = plan.projected_returns;

  return (
    <>
      {!revealed && <PlanRevealModal onAck={() => setRevealed(true)} />}
      <div className={"space-y-6 " + (!revealed ? "blur-sm pointer-events-none select-none" : "")} aria-hidden={!revealed}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <Link to="/step/3" className="text-sm text-gray-500 dark:text-slate-400 hover:text-primary-600">← Back to strategy</Link>
            <h2 className="text-2xl font-bold mt-1">Your investment plan</h2>
          </div>
          <div className="flex gap-2 mt-1 flex-shrink-0">
            <DownloadButton
              href="/api/v2/plan/download.pdf"
              label="PDF"
              ariaLabel="Download plan as PDF"
              enabled={allStagesDone}
            />
            <DownloadButton
              href="/api/v2/plan/download.xlsx"
              label="Excel"
              ariaLabel="Download plan as Excel"
              enabled={allStagesDone}
            />
          </div>
        </div>

      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <Stat value={plan.allocations.length} label="Funds" />
        <Stat value={houses.size} label="Houses" />
        <Stat value={fmtInr(totalSip)} label="Monthly SIP" />
        {pr.bear !== undefined && <Stat value={`${pr.bear}%`} label="Bear CAGR" tone="bear" />}
        {pr.base !== undefined && <Stat value={`${pr.base}%`} label="Base CAGR" tone="base" />}
        {pr.bull !== undefined && <Stat value={`${pr.bull}%`} label="Bull CAGR" tone="bull" />}
      </div>

      {pr.bear !== undefined && pr.base !== undefined && pr.bull !== undefined && totalSip > 0 && (
        <CorpusChart
          monthlySip={totalSip}
          years={profile.investment_horizon_years}
          bear={pr.bear}
          base={pr.base}
          bull={pr.bull}
        />
      )}

      <div className="card card-spacious space-y-3">
        <h3 className="section-title mb-0">Fund allocations</h3>
        <div className="space-y-2">
          {plan.allocations
            .slice()
            .sort((a, b) => b.allocation_pct - a.allocation_pct)
            .map((a, i) => (
              <details key={i} className="group rounded-lg border border-gray-200 dark:border-slate-700 overflow-hidden">
                <summary className="flex items-center gap-3 cursor-pointer px-3 py-2.5 bg-gray-50 dark:bg-slate-700/50 hover:bg-gray-100 dark:hover:bg-slate-700 list-none">
                  <span className="chip flex-shrink-0">{Math.round(a.allocation_pct)}%</span>
                  <span className="flex-1 min-w-0 font-medium text-sm truncate" title={a.fund.name}>
                    {a.fund.display_name || a.fund.name}
                  </span>
                  {a.monthly_sip_inr && (
                    <span className="text-xs text-gray-500 dark:text-slate-400 whitespace-nowrap">{fmtInr(a.monthly_sip_inr)}<span className="hidden sm:inline">/mo</span></span>
                  )}
                  <svg className="w-4 h-4 text-gray-400 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7"/>
                  </svg>
                </summary>
                <div className="px-4 py-3 border-t border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800 space-y-2">
                  <p className="text-xs text-gray-500 dark:text-slate-400">
                    {a.fund.amfi_code && `AMFI: ${a.fund.amfi_code} · `}
                    {a.fund.expense_ratio > 0 && `Expense: ${a.fund.expense_ratio}% · `}
                    {a.fund.category}
                  </p>
                  <Prose text={a.rationale} />
                </div>
              </details>
            ))}
        </div>
      </div>

      {plan.rationale && (
        <div className="card card-spacious">
          <h3 className="section-title">Why this plan</h3>
          <Prose text={plan.rationale} />
        </div>
      )}

      {plan.setup_phase ? (
        <div className="card card-spacious">
          <h3 className="section-title">Getting started</h3>
          <Prose text={plan.setup_phase} />
        </div>
      ) : setupPending ? (
        <SectionSkeleton title="Getting started" />
      ) : null}

      {plan.review_checkpoints && plan.review_checkpoints.length > 0 ? (
        <div className="card card-spacious">
          <h3 className="section-title">Review checkpoints</h3>
          <ul className="space-y-2 text-sm text-gray-700 dark:text-slate-300">
            {plan.review_checkpoints.map((c, i) => (
              <li key={i} className="flex gap-2 items-start">
                <span aria-hidden className="flex-shrink-0 text-primary-500 dark:text-primary-300 font-semibold leading-5 mt-0.5">›</span>
                <span className="leading-5">{c}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : risksPending ? (
        <SectionSkeleton title="Review checkpoints" />
      ) : null}

      {plan.rebalancing_guidelines ? (
        <div className="card card-spacious">
          <h3 className="section-title">Rebalancing</h3>
          <Prose text={plan.rebalancing_guidelines} />
        </div>
      ) : risksPending ? (
        <SectionSkeleton title="Rebalancing" />
      ) : null}

      {plan.risks.length > 0 ? (
        <div className="card card-spacious">
          <h3 className="section-title">Risks to consider</h3>
          <ul className="space-y-2 text-sm text-gray-700 dark:text-slate-300">
            {plan.risks.map((r, i) => (
              <li key={i} className="flex gap-2 items-start">
                <span aria-hidden className="flex-shrink-0 text-red-500 dark:text-red-400 font-semibold leading-5 mt-0.5">⚠</span>
                <span className="leading-5">{r}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : risksPending ? (
        <SectionSkeleton title="Risks to consider" />
      ) : null}

        <p className="text-xs text-red-700 dark:text-red-300 text-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
          {plan.disclaimer}
        </p>
      </div>
    </>
  );
}

function DownloadButton({
  href, label, ariaLabel, enabled,
}: { href: string; label: string; ariaLabel: string; enabled: boolean }) {
  const base = "text-sm px-3 py-1.5 rounded-lg border transition-colors";
  if (!enabled) {
    return (
      <span
        className={base + " border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 text-gray-400 dark:text-slate-500 cursor-not-allowed"}
        aria-label={ariaLabel + " (available when plan is complete)"}
        aria-disabled="true"
        title="Available when plan generation is complete"
      >
        {label}
      </span>
    );
  }
  return (
    <a
      href={href}
      download
      className={base + " border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 hover:border-primary-400 hover:text-primary-600 dark:hover:text-primary-300"}
      aria-label={ariaLabel}
    >
      {label}
    </a>
  );
}

function Stat({ value, label, tone = "primary" }: { value: number | string; label: string; tone?: "primary" | "bear" | "base" | "bull" }) {
  const colour = tone === "bear" ? "text-red-500" : tone === "base" ? "text-amber-500" : tone === "bull" ? "text-green-500" : "text-primary-600 dark:text-primary-300";
  return (
    <div className="card p-3 flex flex-col items-center text-center">
      <span className={`text-xl sm:text-2xl font-bold leading-tight ${colour}`}>{value}</span>
      <span className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-slate-400 mt-1 font-semibold">{label}</span>
    </div>
  );
}
