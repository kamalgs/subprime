import { useLocation } from "react-router-dom";

// Each step: label + Heroicons-style outline SVG path. Icons replace the
// numbered circles so the indicator reads as a journey, not a form counter.
const STEPS: Array<{ label: string; icon: JSX.Element }> = [
  {
    label: "Plan",
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
    ),
  },
  {
    label: "Profile",
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
    ),
  },
  {
    label: "Strategy",
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M3 3v18h18M7 14l4-4 4 4 5-5"/>
    ),
  },
  {
    label: "Plan",
    icon: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/>
    ),
  },
];

function currentStep(path: string): number {
  const m = path.match(/\/step\/(\d)/);
  return m ? Number(m[1]) : 0;
}

export default function StepIndicator() {
  const loc = useLocation();
  const cur = currentStep(loc.pathname);
  // Filled portion of the rail: 0 before step 1, 33/67/100 at subsequent steps
  const fillPct = cur <= 1 ? 0 : cur === 2 ? 33 : cur === 3 ? 67 : 100;

  return (
    <div className="bg-white dark:bg-slate-800 border-b border-gray-100 dark:border-slate-700">
      <div className="max-w-4xl mx-auto px-4 py-5">
        <ol className="relative flex items-start justify-between">
          {/* Rail between first and last pill centres */}
          <div className="absolute top-4 left-4 right-4 h-0.5 bg-gray-200 dark:bg-slate-700 rounded-full" />
          <div
            className="absolute top-4 left-4 h-0.5 bg-gradient-to-r from-primary-500 to-primary-600 rounded-full transition-all duration-700"
            style={{ width: `calc(${fillPct}% - ${(fillPct / 100) * 2}rem)` }}
          />

          {STEPS.map((s, i) => {
            const n = i + 1;
            const done = cur > n;
            const active = cur === n;
            return (
              <li key={n} className="relative z-10 flex flex-col items-center gap-1.5 flex-1 min-w-0">
                {done && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center shadow-sm ring-4 ring-white dark:ring-slate-800">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                )}
                {active && (
                  <div className="relative flex-shrink-0 w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center shadow-md ring-4 ring-white dark:ring-slate-800">
                    <svg className="w-4 h-4 text-white relative z-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {s.icon}
                    </svg>
                    {/* Pulsing halo — 'you are here' */}
                    <span className="absolute inset-0 rounded-full bg-primary-400/60 animate-ping" />
                  </div>
                )}
                {!done && !active && (
                  <div className="flex-shrink-0 w-8 h-8 rounded-full border-2 border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 flex items-center justify-center ring-4 ring-white dark:ring-slate-800">
                    <svg className="w-3.5 h-3.5 text-gray-400 dark:text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {s.icon}
                    </svg>
                  </div>
                )}
                <span
                  className={
                    "text-[11px] sm:text-xs font-semibold " +
                    (done || active
                      ? "text-primary-700 dark:text-primary-300"
                      : "text-gray-400 dark:text-slate-500")
                  }
                >
                  {s.label}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
