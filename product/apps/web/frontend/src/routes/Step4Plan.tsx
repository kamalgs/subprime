import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useState } from "react";
import { getPlan, getPlanStatus, getSession } from "../api/client";
import type { Plan, InvestorProfile } from "../api/types";
import CorpusChart from "../components/CorpusChart";
import PlanRevealModal from "../components/PlanRevealModal";
import Prose from "../components/Prose";

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
  const status = useQuery({
    queryKey: ["plan-status"],
    queryFn: getPlanStatus,
    refetchInterval: (q) => (q.state.data?.ready || q.state.data?.error ? false : 3000),
  });

  const plan = useQuery({
    queryKey: ["plan"],
    queryFn: getPlan,
    enabled: status.data?.ready === true,
  });

  if (status.data?.error && !status.data?.ready) {
    return (
      <div className="card card-spacious max-w-md mx-auto text-center space-y-4 mt-8">
        <h2 className="text-lg font-semibold">Plan generation failed</h2>
        <p className="text-sm text-gray-500 dark:text-slate-400">{status.data.error}</p>
        <Link to="/step/3" className="btn btn-primary">Back to strategy</Link>
      </div>
    );
  }

  if (!status.data?.ready || !plan.data) {
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

  return <PlanView plan={plan.data.plan} profile={plan.data.profile} />;
}

function PlanView({ plan, profile }: { plan: Plan; profile: InvestorProfile }) {
  const session = useQuery({ queryKey: ["session"], queryFn: getSession });
  const [revealed, setRevealed] = useState(
    () => !!sessionStorage.getItem("plan_revealed:" + (session.data?.id ?? "")),
  );
  const totalSip = plan.allocations.reduce((a, x) => a + (x.monthly_sip_inr ?? 0), 0);
  const houses = new Set(plan.allocations.map((a) => a.fund.fund_house).filter(Boolean));
  const pr = plan.projected_returns;

  return (
    <>
      {session.data && !revealed && (
        <PlanRevealModal id={session.data.id} onAck={() => setRevealed(true)} />
      )}
      <div className={"space-y-6 " + (!revealed ? "blur-sm pointer-events-none select-none" : "")} aria-hidden={!revealed}>
        <div>
          <Link to="/step/3" className="text-sm text-gray-500 dark:text-slate-400 hover:text-primary-600">← Back to strategy</Link>
          <h2 className="text-2xl font-bold mt-1">Your investment plan</h2>
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

      {plan.setup_phase && (
        <div className="card card-spacious">
          <h3 className="section-title">Getting started</h3>
          <Prose text={plan.setup_phase} />
        </div>
      )}

      {plan.review_checkpoints && plan.review_checkpoints.length > 0 && (
        <div className="card card-spacious">
          <h3 className="section-title">Review checkpoints</h3>
          <ul className="space-y-2 text-sm text-gray-700 dark:text-slate-300 list-disc list-inside">
            {plan.review_checkpoints.map((c, i) => (
              <li key={i}><Prose text={c} className="inline" /></li>
            ))}
          </ul>
        </div>
      )}

      {plan.rebalancing_guidelines && (
        <div className="card card-spacious">
          <h3 className="section-title">Rebalancing</h3>
          <Prose text={plan.rebalancing_guidelines} />
        </div>
      )}

      {plan.risks.length > 0 && (
        <div className="card card-spacious">
          <h3 className="section-title">Risks to consider</h3>
          <ul className="space-y-2 text-sm text-gray-700 dark:text-slate-300 list-disc list-inside marker:text-red-500">
            {plan.risks.map((r, i) => (
              <li key={i}><Prose text={r} className="inline" /></li>
            ))}
          </ul>
        </div>
      )}

        <p className="text-xs text-red-700 dark:text-red-300 text-center bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
          {plan.disclaimer}
        </p>
      </div>
    </>
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
