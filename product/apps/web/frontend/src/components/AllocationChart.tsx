import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";
import type { StrategyOutline } from "../api/types";

const COLORS: Record<string, string> = {
  Equity: "#6366f1", Debt: "#06b6d4", Gold: "#f59e0b", Other: "#94a3b8",
};

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

export default function AllocationChart({ strategy }: { strategy: StrategyOutline }) {
  const dark = useIsDark();

  const data = [
    { name: "Equity", value: strategy.equity_pct },
    { name: "Debt",   value: strategy.debt_pct },
    { name: "Gold",   value: strategy.gold_pct },
    { name: "Other",  value: strategy.other_pct },
  ].filter((d) => d.value > 0);

  const fg = dark ? "#f1f5f9" : "#0f172a";
  const fgMuted = dark ? "#94a3b8" : "#64748b";
  const bg = dark ? "#1e293b" : "#ffffff";

  // Highlight the largest segment in the centre label.
  const top = data.slice().sort((a, b) => b.value - a.value)[0];

  const option = {
    animation: true,
    animationDuration: 700,
    animationEasing: "cubicOut",
    tooltip: {
      trigger: "item",
      backgroundColor: dark ? "rgba(15, 23, 42, 0.96)" : "rgba(30, 41, 59, 0.95)",
      borderColor: "rgba(255,255,255,0.06)",
      textStyle: { color: "#f8fafc", fontSize: 12 },
      padding: 10,
      formatter: (p: { name: string; value: number; percent: number }) =>
        `<b>${p.name}</b><br/>${p.value}% of portfolio`,
    },
    series: [{
      type: "pie",
      radius: ["62%", "82%"],
      center: ["50%", "50%"],
      avoidLabelOverlap: true,
      startAngle: 90,
      itemStyle: {
        borderRadius: 8,
        borderColor: bg,
        borderWidth: 3,
      },
      label: {
        show: true,
        position: "center",
        formatter: () =>
          `{val|${top?.value ?? 0}%}\n{lbl|${top?.name ?? ""}}`,
        rich: {
          val: { fontSize: 28, fontWeight: 700, color: fg, lineHeight: 32 },
          lbl: { fontSize: 12, color: fgMuted, lineHeight: 18 },
        },
      },
      labelLine: { show: false },
      emphasis: {
        label: {
          show: true,
          position: "center",
          formatter: ({ name, value }: { name: string; value: number }) =>
            `{val|${value}%}\n{lbl|${name}}`,
          rich: {
            val: { fontSize: 28, fontWeight: 700, color: fg, lineHeight: 32 },
            lbl: { fontSize: 12, color: fgMuted, lineHeight: 18 },
          },
        },
        scale: true,
        scaleSize: 6,
      },
      data: data.map((d) => ({
        ...d,
        itemStyle: { color: COLORS[d.name] ?? "#6366f1" },
      })),
    }],
  };

  return (
    <div className="w-full">
      <div style={{ height: 260 }}>
        <ReactECharts
          option={option}
          style={{ height: "100%", width: "100%" }}
          notMerge
          opts={{ renderer: "svg" }}
        />
      </div>
      {/* Legend below — always visible, no overlap with the donut */}
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5 mt-1 text-xs">
        {data.map((d) => (
          <span key={d.name} className="inline-flex items-center gap-1.5 text-gray-700 dark:text-slate-300">
            <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: COLORS[d.name] }} />
            <span className="font-medium">{d.name}</span>
            <span className="text-gray-500 dark:text-slate-400">{d.value}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}
