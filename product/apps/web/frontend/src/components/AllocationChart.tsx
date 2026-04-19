import ReactECharts from "echarts-for-react";
import type { StrategyOutline } from "../api/types";

const COLORS = { Equity: "#4f46e5", Debt: "#0891b2", Gold: "#d97706", Other: "#6b7280" };

export default function AllocationChart({ strategy }: { strategy: StrategyOutline }) {
  const data = [
    { name: "Equity", value: strategy.equity_pct },
    { name: "Debt",   value: strategy.debt_pct },
    { name: "Gold",   value: strategy.gold_pct },
    { name: "Other",  value: strategy.other_pct },
  ].filter((d) => d.value > 0);

  const dark = document.documentElement.classList.contains("dark");

  const option = {
    tooltip: { trigger: "item", formatter: "{b}: {c}%" },
    legend: { bottom: 0, textStyle: { color: dark ? "#cbd5e1" : "#475569" } },
    series: [{
      type: "pie",
      radius: ["55%", "80%"],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 6, borderColor: dark ? "#1e293b" : "#fff", borderWidth: 2 },
      label: { show: false },
      data: data.map((d) => ({ ...d, itemStyle: { color: COLORS[d.name as keyof typeof COLORS] } })),
    }],
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}
