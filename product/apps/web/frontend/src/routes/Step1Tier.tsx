import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import { requestOTP, setTier, verifyOTP } from "../api/client";

export default function Step1Tier() {
  const nav = useNavigate();

  const basic = useMutation({
    mutationFn: () => setTier("basic"),
    onSuccess: () => nav("/step/2"),
  });

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: () => requestOTP(email),
    onSuccess: (r) => { setSent(r.sent); setError(r.sent ? null : r.message); },
    onError: (e: Error) => setError(e.message),
  });

  const verify = useMutation({
    mutationFn: () => verifyOTP(email, code),
    onSuccess: (r) => {
      if (r.verified) nav("/step/2");
      else setError(r.message ?? "Invalid code");
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Choose your plan</h2>
        <p className="mt-2 text-gray-500 dark:text-slate-400">
          Select the advisory experience that fits your needs.
        </p>
      </div>

      {/* mt-4 on the outer grid leaves room for the absolute 'Most popular'
          chip to render without being clipped by the card border on Chrome
          (where the absolute chip at -top-3 was overflowing past its parent). */}
      <div className="grid md:grid-cols-2 gap-4 items-stretch mt-5">
        <div className="card card-spacious flex flex-col h-full">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-bold">Basic</h3>
            <span className="chip chip-neutral">Free</span>
          </div>
          <p className="text-sm text-gray-500 dark:text-slate-400 mb-5">
            A solid research-backed investment plan for your profile.
          </p>
          <ul className="space-y-2 mb-6 flex-1 text-sm">
            <li>✓ Personalised asset allocation</li>
            <li>✓ Top mutual fund recommendations</li>
            <li>✓ SIP amount breakdown</li>
            <li>✓ Goal-based projections</li>
          </ul>
          <button
            className="btn btn-primary w-full py-3"
            onClick={() => basic.mutate()}
            disabled={basic.isPending}
          >
            {basic.isPending ? "Starting…" : "Start free plan"}
          </button>
        </div>

        <div className="card card-spacious flex flex-col h-full relative border-primary-300 dark:border-primary-500">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 z-10">
            <span className="chip shadow-sm">Most popular</span>
          </div>
          <div className="flex items-center justify-between mb-4 mt-2">
            <h3 className="text-xl font-bold">Premium</h3>
            <span className="chip">Premium</span>
          </div>
          <p className="text-sm text-gray-500 dark:text-slate-400 mb-5">
            Deeper analysis with live data, interactive strategy refinement, and
            detailed fund comparisons.
          </p>
          <ul className="space-y-2 mb-6 flex-1 text-sm">
            <li>✓ Everything in Basic</li>
            <li>✓ Live NAV & performance data</li>
            <li>✓ Interactive strategy chat</li>
            <li>✓ Detailed rationale & risk analysis</li>
          </ul>

          {!sent ? (
            <div className="flex gap-2">
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                className="input flex-1 min-w-0"
              />
              <button
                className="btn btn-primary whitespace-nowrap"
                disabled={!email || send.isPending}
                onClick={() => send.mutate()}
              >
                {send.isPending ? "…" : "Send code"}
              </button>
            </div>
          ) : (
            <div className="flex gap-2">
              <input
                type="text"
                inputMode="numeric"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="6-digit code"
                maxLength={6}
                className="input flex-1 min-w-0 tracking-widest text-center"
              />
              <button
                className="btn btn-primary whitespace-nowrap"
                disabled={!code || verify.isPending}
                onClick={() => verify.mutate()}
              >
                {verify.isPending ? "…" : "Verify"}
              </button>
            </div>
          )}
          {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
          {sent && !error && (
            <p className="text-xs text-gray-500 dark:text-slate-400 mt-2">
              Code sent — check your inbox.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
