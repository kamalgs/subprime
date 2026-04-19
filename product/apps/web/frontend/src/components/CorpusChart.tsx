import ReactECharts from "echarts-for-react";

interface Scenario {
  label: string;
  cagr: number;
  future_value: number;
  present_value: number;
  color: string;
}

function fmtInrCompact(v: number): string {
  if (v >= 1e7) return `\u20B9${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `\u20B9${(v / 1e5).toFixed(2)} L`;
  return "\u20B9" + Math.round(v).toLocaleString("en-IN");
}

function buildOption(scenarios: Scenario[], key: "future_value" | "present_value", title: string) {
  const dark = document.documentElement.classList.contains("dark");
  const grid = dark ? "#334155" : "#f1f5f9";
  const textMuted = dark ? "#94a3b8" : "#6b7280";

  return {
    title: { text: title, left: "center", top: 0, textStyle: { fontSize: 12, color: textMuted, fontWeight: 600 } },
    tooltip: {
      trigger: "axis",
      backgroundColor: dark ? "#0f172a" : "#1e293b",
      borderColor: "rgba(255,255,255,0.06)",
      textStyle: { color: "#f8fafc" },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const s = scenarios[params[0].dataIndex];
        return `<b>${s.label}</b> — ${s.cagr}% p.a.<br/>${fmtInrCompact(s[key])}`;
      },
    },
    grid: { top: 32, bottom: 24, left: 56, right: 12 },
    xAxis: {
      type: "category",
      data: scenarios.map((s) => s.label),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: textMuted, fontWeight: 600, fontSize: 11 },
    },
    yAxis: {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: grid } },
      axisLabel: { color: textMuted, fontSize: 10, formatter: fmtInrCompact },
    },
    series: [{
      type: "bar",
      data: scenarios.map((s) => ({ value: s[key], itemStyle: { color: s.color, borderRadius: [6, 6, 0, 0] } })),
      barWidth: "40%",
      animationDuration: 600,
    }],
  };
}

export default function CorpusChart({
  monthlySip, years, bear, base, bull,
}: { monthlySip: number; years: number; bear: number; base: number; bull: number }) {
  if (!monthlySip || !years || !bear || !base || !bull) return null;

  const fv = (cagr: number) => {
    const r = cagr / 100 / 12, n = years * 12;
    return monthlySip * ((Math.pow(1 + r, n) - 1) / r) * (1 + r);
  };
  const pv = (future: number) => future / Math.pow(1 + 0.06, years);

  const scenarios: Scenario[] = [
    { label: "Bear", cagr: bear, future_value: fv(bear), present_value: pv(fv(bear)), color: "#ef4444" },
    { label: "Base", cagr: base, future_value: fv(base), present_value: pv(fv(base)), color: "#f59e0b" },
    { label: "Bull", cagr: bull, future_value: fv(bull), present_value: pv(fv(bull)), color: "#22c55e" },
  ];

  return (
    <div className="card card-spacious space-y-4">
      <div>
        <h3 className="section-title mb-0">Corpus projection</h3>
        <p className="text-sm text-gray-500 dark:text-slate-400 mt-0.5">
          {fmtInrCompact(monthlySip)}/mo SIP &middot; {years}-year horizon &middot; inflation discounted at 6%
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div style={{ height: 220 }}><ReactECharts option={buildOption(scenarios, "future_value", "Future value")} style={{ height: "100%" }} /></div>
        <div style={{ height: 220 }}><ReactECharts option={buildOption(scenarios, "present_value", "In today's \u20B9")} style={{ height: "100%" }} /></div>
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
              <td className="py-3 pr-4 font-semibold">{fmtInrCompact(s.future_value)}</td>
              <td className="py-3 text-gray-600 dark:text-slate-400">{fmtInrCompact(s.present_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
