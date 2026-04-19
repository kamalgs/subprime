import { useLocation } from "react-router-dom";

const STEPS = ["Plan", "Profile", "Strategy", "Plan"];

function currentStep(path: string): number {
  const m = path.match(/\/step\/(\d)/);
  return m ? Number(m[1]) : 0;
}

export default function StepIndicator() {
  const loc = useLocation();
  const cur = currentStep(loc.pathname);
  const fill = cur <= 1 ? 0 : cur === 2 ? 33 : cur === 3 ? 67 : 100;

  return (
    <div className="bg-white dark:bg-slate-800 border-b border-gray-100 dark:border-slate-700">
      <div className="max-w-4xl mx-auto px-4 py-5">
        <ol className="relative flex items-start justify-between">
          <div className="absolute top-4 left-4 right-4 h-0.5 bg-gray-200 dark:bg-slate-700 rounded-full" />
          <div
            className="absolute top-4 left-4 h-0.5 bg-primary-500 rounded-full transition-all duration-700"
            style={{ width: `calc(${fill}% - ${(fill / 100) * 2}rem)` }}
          />
          {STEPS.map((label, i) => {
            const n = i + 1;
            const done = cur > n;
            const active = cur === n;
            return (
              <li key={n} className="relative z-10 flex flex-col items-center gap-1 flex-1 min-w-0">
                <div
                  className={
                    "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ring-4 ring-white dark:ring-slate-800 " +
                    (done || active
                      ? "bg-primary-600 text-white"
                      : "border-2 border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 text-gray-500 dark:text-slate-400")
                  }
                >
                  {done ? "✓" : n}
                </div>
                <span
                  className={
                    "text-[11px] font-semibold " +
                    (done || active
                      ? "text-primary-700 dark:text-primary-300"
                      : "text-gray-400 dark:text-slate-500")
                  }
                >
                  {label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
