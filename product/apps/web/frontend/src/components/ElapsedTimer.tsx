import { useEffect, useState } from "react";

/** Counts elapsed seconds since the component mounted. */
export default function ElapsedTimer({
  className = "",
  prefix = "",
  suffix = "",
}: {
  className?: string;
  prefix?: string;
  suffix?: string;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = performance.now();
    const id = setInterval(() => setElapsed((performance.now() - start) / 1000), 100);
    return () => clearInterval(id);
  }, []);

  return (
    <span className={className} aria-live="polite" aria-atomic="true">
      {prefix}
      {elapsed.toFixed(1)}s
      {suffix}
    </span>
  );
}
