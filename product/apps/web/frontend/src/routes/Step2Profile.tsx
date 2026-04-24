import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  getPersonas, selectPersona, submitProfile,
} from "../api/client";
import DocumentsUpload from "../components/DocumentsUpload";
import type { Archetype, Risk } from "../api/types";

const GOALS = [
  ["retirement", "Retirement"],
  ["children_education", "Children's education"],
  ["house_purchase", "House purchase"],
  ["wealth_building", "Wealth building"],
  ["emergency_fund", "Emergency fund"],
  ["other", "Other"],
] as const;

const LIFE_STAGES = [
  ["student", "Student"],
  ["early career", "Early career (20s)"],
  ["mid career", "Mid career (30s–40s)"],
  ["pre-retirement", "Pre-retirement (50s)"],
  ["retirement", "Retirement (60s+)"],
] as const;

export default function Step2Profile() {
  const nav = useNavigate();
  const { data } = useQuery({ queryKey: ["personas"], queryFn: getPersonas });
  const [tab, setTab] = useState<"quick" | "custom">("quick");

  const persona = useMutation({
    mutationFn: selectPersona,
    onSuccess: () => nav("/step/3"),
  });

  /** Prefill the custom form with an archetype's defaults and switch to the
   *  Custom tab. The user can review/edit before submitting — e.g. fill in
   *  their real name instead of 'Early career'. */
  const apply = (a: Archetype) => {
    setTab("custom");
    setForm({
      name: "", age: a.age, monthly_sip: a.monthly_sip_inr,
      existing_corpus: a.existing_corpus_inr, risk: a.risk_appetite,
      horizon: a.investment_horizon_years, life_stage: a.life_stage,
      goals: new Set(a.financial_goals.map((g) => g.toLowerCase().replace(/[^a-z]+/g, "_"))),
      preferences: "",
    });
  };

  const [form, setForm] = useState({
    name: "", age: 30, monthly_sip: 25000, existing_corpus: 500000,
    risk: "moderate" as Risk, horizon: 15, life_stage: "mid career",
    goals: new Set<string>(["wealth_building"]),
    preferences: "",
  });

  const [saved, setSaved] = useState(false);

  const submit = useMutation({
    mutationFn: () =>
      submitProfile({
        name: form.name,
        age: form.age,
        monthly_sip_inr: form.monthly_sip,
        existing_corpus_inr: form.existing_corpus,
        risk_appetite: form.risk,
        investment_horizon_years: form.horizon,
        life_stage: form.life_stage,
        financial_goals: [...form.goals],
        preferences: form.preferences || null,
      }),
    onSuccess: () => setSaved(true),
  });

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Your investor profile</h2>
        <p className="mt-2 text-gray-500 dark:text-slate-400">
          Pick a starting point — you can edit any detail before continuing.
        </p>
      </div>

      <div className="flex rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-100 dark:bg-slate-800 p-1 max-w-xs mx-auto gap-1">
        {(["quick", "custom"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={
              "flex-1 py-2 px-4 rounded-lg text-sm font-semibold transition " +
              (tab === t
                ? "bg-white dark:bg-slate-700 text-primary-700 dark:text-primary-300 shadow-sm"
                : "text-gray-500 dark:text-slate-400")
            }
          >
            {t === "quick" ? "Quick start" : "Custom"}
          </button>
        ))}
      </div>

      {tab === "quick" && (
        data?.personas ? (
          // Demo session — full research persona bank submits directly
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.personas.map((p) => (
              <button
                key={p.id}
                onClick={() => persona.mutate(p.id)}
                className="card text-left hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-md transition group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold truncate">{p.name}</p>
                    <p className="text-xs text-gray-500 dark:text-slate-400">
                      Age {p.age} · {p.investment_horizon_years}yr horizon
                    </p>
                  </div>
                  <span className="chip chip-neutral">{p.risk_appetite}</span>
                </div>
                <p className="text-xs text-gray-500 dark:text-slate-400">
                  ₹{p.monthly_investible_surplus_inr.toLocaleString("en-IN")}/mo SIP
                </p>
              </button>
            ))}
          </div>
        ) : (
          // Regular session — three archetype cards that prefill the custom form
          <div>
            <p className="text-center text-sm text-gray-500 dark:text-slate-400 -mt-2 mb-3">
              Pick a starting point — edit any detail before continuing.
            </p>
            <div className="grid sm:grid-cols-3 gap-3">
              {data?.archetypes.map((a) => (
                <button
                  key={a.id}
                  onClick={() => apply(a)}
                  className="card text-left hover:border-primary-400 dark:hover:border-primary-500 hover:shadow-md transition"
                >
                  <div className="flex items-center justify-between gap-2 mb-2">
                    <p className="font-semibold">{a.name}</p>
                    <span className="chip chip-neutral">{a.risk_appetite}</span>
                  </div>
                  <p className="text-sm text-gray-500 dark:text-slate-400">{a.blurb}</p>
                  <p className="mt-3 text-xs font-medium text-primary-600 dark:text-primary-300">
                    Start from this →
                  </p>
                </button>
              ))}
            </div>
          </div>
        )
      )}

      {tab === "custom" && (
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            submit.mutate();
          }}
        >
          <section className="card card-spacious space-y-5">
            <h3 className="section-title mb-0">About you</h3>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="field-label">Full name</label>
                <input required className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Ravi Kumar" />
              </div>
              <div>
                <label className="field-label">Age</label>
                <input required type="number" min={18} max={80} className="input" value={form.age} onChange={(e) => setForm({ ...form, age: Number(e.target.value) })} />
              </div>
            </div>

            <div>
              <label className="field-label">Life stage</label>
              <select required className="input" value={form.life_stage} onChange={(e) => setForm({ ...form, life_stage: e.target.value })}>
                {LIFE_STAGES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>

            <div>
              <span className="field-label">Risk appetite</span>
              <div className="grid grid-cols-3 gap-2">
                {(["conservative", "moderate", "aggressive"] as const).map((r) => (
                  <label key={r} className="cursor-pointer">
                    <input type="radio" name="risk" value={r} checked={form.risk === r} onChange={() => setForm({ ...form, risk: r })} className="peer sr-only" />
                    <div className="rounded-lg border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-3 py-2.5 text-center transition-all peer-checked:border-primary-500 peer-checked:bg-primary-50 dark:peer-checked:bg-primary-900/40">
                      <div className="text-sm font-medium capitalize">{r}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <label className="field-label">
                Investment horizon — <span className="text-primary-700 dark:text-primary-300 font-semibold">{form.horizon} years</span>
              </label>
              <input type="range" min={1} max={40} value={form.horizon} onChange={(e) => setForm({ ...form, horizon: Number(e.target.value) })} className="w-full h-2 bg-gray-200 dark:bg-slate-700 rounded-lg appearance-none accent-primary-600" />
            </div>
          </section>

          <section className="card card-spacious space-y-5">
            <h3 className="section-title mb-0">Money and goals</h3>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="field-label">Monthly SIP (₹)</label>
                <input required type="number" min={0} className="input" value={form.monthly_sip} onChange={(e) => setForm({ ...form, monthly_sip: Number(e.target.value) })} />
              </div>
              <div>
                <label className="field-label">Existing corpus (₹)</label>
                <input required type="number" min={0} className="input" value={form.existing_corpus} onChange={(e) => setForm({ ...form, existing_corpus: Number(e.target.value) })} />
              </div>
            </div>

            <div>
              <span className="field-label">Financial goals</span>
              <div className="grid sm:grid-cols-2 gap-2">
                {GOALS.map(([v, l]) => (
                  <label key={v} className="flex items-center gap-2 cursor-pointer rounded-md px-2 py-1.5 hover:bg-gray-50 dark:hover:bg-slate-700/50">
                    <input type="checkbox" checked={form.goals.has(v)} onChange={(e) => {
                      const s = new Set(form.goals);
                      if (e.target.checked) s.add(v); else s.delete(v);
                      setForm({ ...form, goals: s });
                    }} className="rounded border-gray-300 text-primary-600 focus:ring-primary-400" />
                    <span className="text-sm">{l}</span>
                  </label>
                ))}
              </div>
            </div>

            <details className="group border-t border-gray-100 dark:border-slate-700 pt-4">
              <summary className="text-sm text-gray-500 dark:text-slate-400 cursor-pointer">
                Any specific preferences? <span className="text-gray-400">(optional)</span>
              </summary>
              <textarea rows={3} className="input mt-3 resize-none" value={form.preferences} onChange={(e) => setForm({ ...form, preferences: e.target.value })} placeholder="e.g. Prefer index funds, avoid tobacco sector" />
            </details>
          </section>

          {!saved ? (
            <button type="submit" className="btn btn-primary w-full py-3 text-base" disabled={submit.isPending}>
              {submit.isPending ? "Saving…" : "Save profile"}
            </button>
          ) : (
            <div className="space-y-4">
              <DocumentsUpload />
              <button
                type="button"
                className="btn btn-primary w-full py-3 text-base"
                onClick={() => nav("/step/3")}
              >
                Build my plan →
              </button>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
