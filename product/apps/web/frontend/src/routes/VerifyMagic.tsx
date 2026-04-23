import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { verifyOTP } from "../api/client";

export default function VerifyMagic() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const email = params.get("email") || "";
    const code = params.get("code") || "";
    if (!email || !code) {
      setError("Missing email or code in the link.");
      return;
    }
    verifyOTP(email, code)
      .then((r) => {
        if (r.verified) nav("/step/2", { replace: true });
        else setError(r.message || "Link has expired or is invalid.");
      })
      .catch((e) => setError(e.message || "Verification failed."));
  }, [params, nav]);

  return (
    <div className="card card-spacious max-w-md mx-auto text-center space-y-4 mt-8">
      {error ? (
        <>
          <h2 className="text-lg font-semibold">Couldn't verify</h2>
          <p className="text-sm text-gray-500 dark:text-slate-400">{error}</p>
          <a href="/step/1" className="btn btn-primary">Start over</a>
        </>
      ) : (
        <>
          <div className="w-10 h-10 border-4 border-primary-200 dark:border-slate-700 border-t-primary-600 rounded-full animate-spin mx-auto" />
          <p className="text-sm text-gray-500 dark:text-slate-400">Verifying your code…</p>
        </>
      )}
    </div>
  );
}
