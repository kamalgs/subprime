import ReactECharts from "echarts-for-react";
import { useEffect, useMemo, useState } from "react";

interface Scenario {
  label: string;
  cagr: number;
  future_value: number;
  present_value: number;
  color: string;
}

function fmt(v: number): string {
  if (!v) return "\u20B90";
  if (v >= 1e7) return `\u20B9${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `\u20B9${(v / 1e5).toFixed(2)} L`;
  return "\u20B9" + Math.round(v).toLocaleString("en-IN");
}

function useIsDark() {
  const [dark, setDark] = useState(
    () => document.documentElement.classList.contains("dark"),
  );
  useEffect(() => {
    const obs = new MutationObserver(() =>
      setDark(document.documentElement.classList.contains("dark")),
    );
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

function buildOption(
  scenarios: Scenario[],
  key: "future_value" | "present_value",
  title: string,
  dark: boolean,
) {
  const gridLine = dark ? "#334155" : "#e2e8f0";
  const axisLabel = dark ? "#94a3b8" : "#64748b";
  const titleColor = dark ? "#e2e8f0" : "#334155";

  return {
    animation: true,
    animationDuration: 600,
    animationEasing: "cubicOut",
    title: {
      text: title,
      left: "center",
      top: 0,
      textStyle: { fontSize: 12, color: titleColor, fontWeight: 600 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: dark ? "rgba(15, 23, 42, 0.96)" : "rgba(30, 41, 59, 0.95)",
      borderColor: "rgba(255,255,255,0.06)",
      textStyle: { color: "#f8fafc", fontSize: 12 },
      padding: 10,
      formatter: (params: Array<{ dataIndex: number }>) => {
        const s = scenarios[params[0].dataIndex];
        return `<b>${s.label}</b> — ${s.cagr}% p.a.<br/>${fmt(s[key])}`;
      },
    },
    grid: { top: 32, bottom: 24, left: 60, right: 10, containLabel: false },
    xAxis: {
      type: "category",
      data: scenarios.map((s) => s.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: axisLabel, fontWeight: 600, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: gridLine, type: [4, 4], dashOffset: 0 } as const },
      axisLabel: { color: axisLabel, fontSize: 10, formatter: fmt },
    },
    series: [{
      type: "bar",
      data: scenarios.map((s) => ({
        value: s[key],
        itemStyle: {
          // Use a vertical gradient for visual richness
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: s.color },
              { offset: 1, color: s.color + "bb" },
            ],
          },
          borderRadius: [8, 8, 0, 0],
          shadowBlur: 8,
          shadowColor: s.color + "33",
          shadowOffsetY: 2,
        },
      })),
      barWidth: "42%",
      label: {
        show: true,
        position: "top",
        formatter: (p: { value: number }) => fmt(p.value),
        fontSize: 10,
        color: axisLabel,
        fontWeight: 600,
      },
    }],
  };
}

type View = "future" | "today";

export default function CorpusChart({
  monthlySip, years, bear, base, bull,
}: { monthlySip: number; years: number; bear: number; base: number; bull: number }) {
  const dark = useIsDark();
  const [view, setView] = useState<View>("future");

  const scenarios: Scenario[] | null = useMemo(() => {
    if (!monthlySip || !years || !bear || !base || !bull) return null;
    const fv = (cagr: number) => {
      const r = cagr / 100 / 12, n = years * 12;
      return monthlySip * ((Math.pow(1 + r, n) - 1) / r) * (1 + r);
    };
    const pv = (future: number) => future / Math.pow(1 + 0.06, years);
    return [
      { label: "Bear", cagr: bear, future_value: fv(bear), present_value: pv(fv(bear)), color: "#ef4444" },
      { label: "Base", cagr: base, future_value: fv(base), present_value: pv(fv(base)), color: "#f59e0b" },
      { label: "Bull", cagr: bull, future_value: fv(bull), present_value: pv(fv(bull)), color: "#22c55e" },
    ];
  }, [monthlySip, years, bear, base, bull]);

  if (!scenarios) return null;

  const activeKey: "future_value" | "present_value" = view === "future" ? "future_value" : "present_value";
  const activeTitle = view === "future" ? "Future value" : "In today's \u20B9";

  return (
    <div className="card card-spacious space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="section-title mb-0">Corpus projection</h3>
          <p className="text-sm text-gray-500 dark:text-slate-400 mt-0.5">
            {fmt(monthlySip)}/mo SIP &middot; {years}-year horizon &middot; inflation discounted at 6%
          </p>
        </div>
        {/* Segmented control — single chart, two views */}
        <div role="tablist" aria-label="Value view"
             className="inline-flex rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-900/40 p-0.5">
          {([
            ["future", "Future value"],
            ["today",  "Today's \u20B9"],
          ] as const).map(([v, label]) => (
            <button
              key={v}
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              className={
                "px-3 py-1.5 text-xs font-semibold rounded-md transition-colors " +
                (view === v
                  ? "bg-white dark:bg-slate-700 text-primary-700 dark:text-primary-300 shadow-sm"
                  : "text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200")
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ height: 260 }}>
        <ReactECharts
          option={buildOption(scenarios, activeKey, activeTitle, dark)}
          style={{ height: "100%" }}
          notMerge
          opts={{ renderer: "svg" }}
        />
      </div>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-slate-700 text-left text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400">
            <th className="py-2 pr-4">Scenario</th>
            <th className="py-2 pr-4">CAGR</th>
            <th className="py-2 pr-4">Future value</th>
            <th className="py-2">Today's ₹</th>
          </tr>
        </thead>
        <tbody>
          {scenarios.map((s) => (
            <tr key={s.label} className="border-b border-gray-100 dark:border-slate-700 last:border-0">
              <td className="py-3 pr-4">
                <span className="inline-flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
                  <span style={{ color: s.color }} className="font-medium">{s.label}</span>
                </span>
              </td>
              <td className="py-3 pr-4">{s.cagr}% p.a.</td>
              <td className="py-3 pr-4 font-semibold text-gray-900 dark:text-slate-100">{fmt(s.future_value)}</td>
              <td className="py-3 text-gray-600 dark:text-slate-400">{fmt(s.present_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
