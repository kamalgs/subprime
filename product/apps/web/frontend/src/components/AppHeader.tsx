import { useEffect, useState } from "react";

export default function AppHeader() {
  const [dark, setDark] = useState<boolean>(
    () => document.documentElement.classList.contains("dark"),
  );

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <header className="bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700 shadow-sm">
      <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
        <img
          src="/static/icon-192.svg"
          alt=""
          className="w-10 h-10 rounded-full flex-shrink-0 ring-1 ring-amber-200 dark:ring-amber-800/40"
        />
        <div className="flex flex-col flex-1 min-w-0">
          {/* Two-tone wordmark: serif 'Ben' in indigo + italic serif 'ji' in amber.
              Mirrors the monogram on the coin mark. */}
          <h1 className="text-[28px] leading-none font-serif font-bold tracking-tight">
            <span className="text-primary-700 dark:text-primary-300">Ben</span>
            <span className="italic text-amber-600 dark:text-amber-400">ji</span>
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-slate-400 truncate">
            Your personal mutual fund advisor for Indian investors
          </p>
        </div>
        <button
          type="button"
          aria-label="Toggle theme"
          onClick={() => setDark(!dark)}
          className="w-9 h-9 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-gray-50 dark:hover:bg-slate-700 flex items-center justify-center flex-shrink-0"
        >
          <span aria-hidden>{dark ? "☀" : "☾"}</span>
        </button>
      </div>
    </header>
  );
}
