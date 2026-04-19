import { useEffect, useState } from "react";

const COOKIE = "sebi_ack";

function hasAck(): boolean {
  return document.cookie.split("; ").some((c) => c.startsWith(COOKIE + "=1"));
}

export default function SebiModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!hasAck()) setOpen(true);
  }, []);

  if (!open) return null;

  const dismiss = () => {
    const exp = new Date();
    exp.setFullYear(exp.getFullYear() + 1);
    document.cookie = `${COOKIE}=1; expires=${exp.toUTCString()}; path=/; SameSite=Lax`;
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-red-50 dark:bg-red-900/30 flex items-center justify-center flex-shrink-0">
            <span className="text-red-600 dark:text-red-400 text-xl">⚠</span>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-slate-100 mb-1">
              Before you continue
            </h2>
            <p className="text-sm text-gray-600 dark:text-slate-300 leading-relaxed">
              This tool is for{" "}
              <span className="font-medium text-gray-900 dark:text-slate-100">
                research and educational purposes only
              </span>
              . It is not registered with SEBI and does not constitute financial advice.
              Consult a SEBI-registered investment advisor before making any investment
              decisions.
            </p>
          </div>
        </div>
        <button onClick={dismiss} className="btn btn-primary w-full">
          I understand
        </button>
      </div>
    </div>
  );
}
