import { useState } from "react";
import {
  extractDocuments,
  removeDocument,
  setDocumentPassword,
  stageDocuments,
  type StagedDoc,
} from "../api/client";

function fmtInr(v: number): string {
  if (!v) return "\u20B90";
  if (v >= 1e7) return `\u20B9${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `\u20B9${(v / 1e5).toFixed(2)} L`;
  return "\u20B9" + Math.round(v).toLocaleString("en-IN");
}

const TYPE_LABEL: Record<string, string> = {
  cas: "Mutual Fund Holdings (CAS)",
  cibil: "Credit Report (CIBIL)",
  unknown: "Unrecognised",
};

export default function DocumentsUpload({ onExtracted }: { onExtracted?: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [docs, setDocs] = useState<StagedDoc[]>([]);
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [pwErrors, setPwErrors] = useState<Record<string, string>>({});
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<Awaited<ReturnType<typeof extractDocuments>> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onFilesChosen = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    try {
      const r = await stageDocuments(Array.from(files));
      setDocs(r.documents);
      if (r.errors.length) {
        setError(r.errors.map((e) => `${e.filename}: ${e.error}`).join("; "));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    }
  };

  const applyPw = async (doc: StagedDoc) => {
    const pw = (passwords[doc.doc_id] || "").trim();
    if (!pw) return;
    try {
      const updated = await setDocumentPassword(doc.doc_id, pw);
      setDocs((prev) => prev.map((d) => (d.doc_id === doc.doc_id ? updated : d)));
      setPwErrors((prev) => ({ ...prev, [doc.doc_id]: "" }));
    } catch (e) {
      setPwErrors((prev) => ({
        ...prev,
        [doc.doc_id]: e instanceof Error ? e.message : "Wrong password",
      }));
    }
  };

  const onRemove = async (docId: string) => {
    await removeDocument(docId);
    setDocs((prev) => prev.filter((d) => d.doc_id !== docId));
  };

  const onExtract = async () => {
    setExtracting(true);
    setError(null);
    try {
      const r = await extractDocuments();
      setResult(r);
      setDocs([]);
      onExtracted?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setExtracting(false);
    }
  };

  const allVerified = docs.length > 0 && docs.every((d) => d.verified);

  if (result) {
    return (
      <div className="card card-spacious space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="section-title mb-0">Documents processed</h3>
          <span className="chip">Done</span>
        </div>
        <ul className="text-sm space-y-1">
          {result.holdings_count > 0 && (
            <li>
              <b>{result.holdings_count}</b> mutual-fund holdings,
              total <b>{fmtInr(result.holdings_total_inr)}</b>
            </li>
          )}
          {result.credit_summary && (
            <li>
              Credit report: <b>{result.credit_summary.active_account_count}</b> active accounts,
              outstanding <b>{fmtInr(result.credit_summary.total_outstanding_inr)}</b>
              {result.credit_summary.has_overdue && (
                <span className="text-red-600 ml-2">· overdue flagged</span>
              )}
            </li>
          )}
          {result.skipped.map((s) => (
            <li key={s.doc_id} className="text-gray-500">
              Skipped {s.filename}: {s.reason}
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="card card-spacious space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="section-title mb-0">Supporting documents</h3>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">
            Optional — upload your CAS and/or CIBIL report so Benji can see your real portfolio and debt.
          </p>
        </div>
        {!expanded && (
          <button type="button" className="btn text-sm" onClick={() => setExpanded(true)}>
            Upload documents
          </button>
        )}
      </div>

      {expanded && (
        <div className="space-y-3 pt-2 border-t border-gray-100 dark:border-slate-700">
          <p className="text-xs text-gray-500 dark:text-slate-400">
            Don't have them?{" "}
            <a
              href="https://www.camsonline.com/Investors/Statements/Consolidated-Account-Statement"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              Request CAS →
            </a>{" · "}
            <a
              href="https://www.cibil.com/freecibilscore"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              Free CIBIL report →
            </a>
          </p>

          <input
            type="file"
            accept="application/pdf"
            multiple
            onChange={(e) => onFilesChosen(e.target.files)}
            className="input text-sm file:mr-3 file:border-0 file:bg-gray-100 dark:file:bg-slate-700 file:px-3 file:py-1 file:rounded"
          />

          {docs.length > 0 && (
            <ul className="space-y-2">
              {docs.map((d) => (
                <li
                  key={d.doc_id}
                  className="border border-gray-200 dark:border-slate-700 rounded-lg p-3 space-y-2"
                >
                  <div className="flex items-center gap-2 text-sm">
                    <span className="flex-shrink-0">
                      {d.verified ? (
                        <span className="text-green-600" aria-label="verified">✓</span>
                      ) : d.requires_password ? (
                        <span className="text-amber-500" aria-label="needs password">🔒</span>
                      ) : (
                        <span className="text-gray-400">•</span>
                      )}
                    </span>
                    <span className="flex-1 truncate font-medium">{d.filename}</span>
                    <span className="text-xs text-gray-500 dark:text-slate-400">
                      {TYPE_LABEL[d.detected_type] ?? d.detected_type}
                    </span>
                    <button
                      type="button"
                      onClick={() => onRemove(d.doc_id)}
                      className="text-xs text-gray-400 hover:text-red-600"
                      aria-label="remove"
                    >
                      ✕
                    </button>
                  </div>
                  {d.requires_password && !d.verified && (
                    <div className="flex gap-2">
                      <input
                        type="password"
                        placeholder="PDF password"
                        value={passwords[d.doc_id] || ""}
                        onChange={(e) =>
                          setPasswords({ ...passwords, [d.doc_id]: e.target.value })
                        }
                        className="input text-sm flex-1"
                      />
                      <button
                        type="button"
                        className="btn text-sm"
                        disabled={!(passwords[d.doc_id] || "").trim()}
                        onClick={() => applyPw(d)}
                      >
                        Unlock
                      </button>
                    </div>
                  )}
                  {pwErrors[d.doc_id] && (
                    <p className="text-xs text-red-600">{pwErrors[d.doc_id]}</p>
                  )}
                </li>
              ))}
            </ul>
          )}

          {error && <p className="text-xs text-red-600">{error}</p>}

          {docs.length > 0 && (
            <button
              type="button"
              className="btn btn-primary w-full"
              disabled={!allVerified || extracting}
              onClick={onExtract}
            >
              {extracting
                ? "Extracting…"
                : !allVerified
                ? "Unlock all documents to continue"
                : `Extract ${docs.length} document${docs.length > 1 ? "s" : ""}`}
            </button>
          )}

          <p className="text-[11px] text-gray-400 dark:text-slate-500">
            PDFs are parsed in memory and discarded after extraction — not stored on our servers.
          </p>
        </div>
      )}
    </div>
  );
}
