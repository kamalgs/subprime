import { useState } from "react";
import { uploadCAS } from "../api/client";

type Holding = { scheme: string; category: string; value_inr: number; units: number };

function fmtInr(v: number): string {
  if (!v) return "\u20B90";
  if (v >= 1e7) return `\u20B9${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `\u20B9${(v / 1e5).toFixed(2)} L`;
  return "\u20B9" + Math.round(v).toLocaleString("en-IN");
}

export default function CASUpload({
  onParsed,
}: {
  onParsed?: (total: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{
    holdings: Holding[];
    total: number;
  } | null>(null);

  const onUpload = async () => {
    if (!file || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      const r = await uploadCAS(file, password);
      setResult({ holdings: r.holdings, total: r.total_value_inr });
      onParsed?.(r.total_value_inr);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Upload failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    // Roll up by category for a quick allocation chip row
    const byCat = new Map<string, number>();
    for (const h of result.holdings) {
      byCat.set(h.category, (byCat.get(h.category) ?? 0) + h.value_inr);
    }
    const cats = [...byCat.entries()].sort((a, b) => b[1] - a[1]);
    return (
      <div className="card card-spacious space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="section-title mb-0">Your current holdings</h3>
          <span className="text-sm text-gray-500 dark:text-slate-400">
            {result.holdings.length} funds · {fmtInr(result.total)}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {cats.map(([cat, val]) => (
            <span key={cat} className="chip">
              {cat}: {((val / result.total) * 100).toFixed(0)}%
            </span>
          ))}
        </div>
        <details>
          <summary className="cursor-pointer text-sm text-primary-600 hover:text-primary-700">
            See {result.holdings.length} holdings
          </summary>
          <ul className="mt-2 space-y-1 text-sm">
            {result.holdings
              .slice()
              .sort((a, b) => b.value_inr - a.value_inr)
              .map((h) => (
                <li key={h.scheme} className="flex gap-2 items-baseline">
                  <span className="text-gray-400 dark:text-slate-500 text-xs w-16 flex-shrink-0">
                    {h.category}
                  </span>
                  <span className="flex-1 truncate" title={h.scheme}>
                    {h.scheme}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-slate-400 font-mono">
                    {fmtInr(h.value_inr)}
                  </span>
                </li>
              ))}
          </ul>
        </details>
      </div>
    );
  }

  return (
    <div className="card card-spacious space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="section-title mb-0">Current portfolio</h3>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
            Optional — upload a CAS to auto-fill your holdings.
          </p>
        </div>
        {!expanded && (
          <button
            type="button"
            className="btn text-sm"
            onClick={() => setExpanded(true)}
          >
            I have a CAS
          </button>
        )}
      </div>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-gray-100 dark:border-slate-700">
          <p className="text-xs text-gray-500 dark:text-slate-400">
            Don't have one?{" "}
            <a
              href="https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              Request from CAMS →
            </a>
            {" · "}
            <a
              href="https://mfs.kfintech.com/investor/General/ConsolidatedAccountStatement"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              KFintech →
            </a>
            {" "}
            Pick <b>Detailed</b> + <b>With holdings</b>. PDF arrives in ~10 min.
          </p>
          <div className="flex gap-2 flex-wrap">
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="input text-sm file:mr-3 file:border-0 file:bg-gray-100 dark:file:bg-slate-700 file:px-3 file:py-1 file:rounded"
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="PDF password (PAN)"
              className="input text-sm min-w-40 flex-1"
            />
            <button
              type="button"
              className="btn btn-primary text-sm whitespace-nowrap"
              disabled={!file || !password || submitting}
              onClick={onUpload}
            >
              {submitting ? "Parsing…" : "Parse CAS"}
            </button>
          </div>
          {error && (
            <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
          )}
          <p className="text-[11px] text-gray-400 dark:text-slate-500">
            The PDF is parsed in memory and discarded — not stored on our servers.
          </p>
        </div>
      )}
    </div>
  );
}
