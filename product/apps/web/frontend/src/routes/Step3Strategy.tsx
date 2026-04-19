import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  answerQuestions, generatePlan, generateStrategy, reviseStrategy,
} from "../api/client";
import AllocationChart from "../components/AllocationChart";

export default function Step3Strategy() {
  const nav = useNavigate();
  const qc = useQueryClient();

  // generateStrategy is a POST — treat as mutation but cached at start of page.
  const { data, isPending, error } = useQuery({
    queryKey: ["strategy"],
    queryFn: generateStrategy,
    staleTime: Infinity,
    retry: false,
  });

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [chat, setChat] = useState("");

  const answerMut = useMutation({
    mutationFn: (feedback: string) => answerQuestions(feedback),
    onSuccess: (r) => qc.setQueryData(["strategy"], r),
  });
  const reviseMut = useMutation({
    mutationFn: (feedback: string) => reviseStrategy(feedback),
    onSuccess: (r) => { qc.setQueryData(["strategy"], r); setChat(""); },
  });
  const planMut = useMutation({
    mutationFn: generatePlan,
    onSuccess: () => nav("/step/4"),
  });

  if (isPending) {
    return (
      <div className="card card-spacious max-w-md mx-auto text-center space-y-3 mt-8">
        <div className="w-10 h-10 border-4 border-primary-200 dark:border-slate-700 border-t-primary-600 rounded-full animate-spin mx-auto" />
        <p className="text-sm text-gray-500 dark:text-slate-400">
          Generating your personalised strategy…
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="card card-spacious max-w-md mx-auto text-center">
        <p className="text-red-600">{(error as Error)?.message ?? "Failed to load strategy."}</p>
      </div>
    );
  }

  const s = data.strategy;

  return (
    <div className="space-y-5">
      <div className="grid md:grid-cols-2 gap-5">
        <div className="card card-spacious">
          <h3 className="section-title">Asset allocation</h3>
          <AllocationChart strategy={s} />
        </div>
        <div className="card card-spacious space-y-4">
          <div>
            <h3 className="section-title">Equity approach</h3>
            <p className="text-sm text-gray-600 dark:text-slate-300 leading-relaxed">
              {s.equity_approach}
            </p>
          </div>
          <div>
            <h3 className="section-title">Key themes</h3>
            <div className="flex flex-wrap gap-2">
              {s.key_themes.map((t) => <span key={t} className="chip">{t}</span>)}
            </div>
          </div>
          <div className="rounded-lg bg-gray-50 dark:bg-slate-700/50 border border-gray-200 dark:border-slate-700 p-3">
            <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-slate-400 mb-1">
              Risk / return
            </p>
            <p className="text-sm text-gray-700 dark:text-slate-300">{s.risk_return_summary}</p>
          </div>
        </div>
      </div>

      {s.open_questions.length > 0 && (
        <div className="card card-spacious bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 space-y-3">
          <div>
            <h3 className="text-base font-semibold">A few questions to sharpen the plan</h3>
            <p className="text-sm text-gray-600 dark:text-slate-300 mt-1">Optional — answer any that apply.</p>
          </div>
          {s.open_questions.map((q) => (
            <div key={q} className="rounded-lg bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 p-3 space-y-2">
              <p className="text-sm font-medium">{q}</p>
              <textarea
                rows={2}
                placeholder="Your thoughts…"
                className="input resize-none"
                value={answers[q] ?? ""}
                onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })}
              />
            </div>
          ))}
          <button
            className="btn btn-primary w-full"
            disabled={answerMut.isPending}
            onClick={() => {
              const parts = Object.entries(answers).filter(([, v]) => v.trim()).map(([k, v]) => `${k}: ${v.trim()}`);
              if (!parts.length) return;
              answerMut.mutate("Answers to open questions:\n" + parts.join("\n"));
            }}
          >
            {answerMut.isPending ? "Updating…" : "Update strategy with my inputs"}
          </button>
        </div>
      )}

      <div className="card card-spacious space-y-3">
        <h3 className="text-sm font-medium">Anything else to adjust?</h3>
        {data.chat.length > 0 && (
          <div className="space-y-2">
            {data.chat.map((t, i) => (
              <div key={i} className={"flex " + (t.role === "user" ? "justify-end" : "justify-start")}>
                <div className={"max-w-xs sm:max-w-sm px-3 py-2 rounded-2xl text-sm " + (t.role === "user" ? "bg-primary-600 text-white" : "bg-gray-100 dark:bg-slate-700 border border-gray-200 dark:border-slate-600")}>
                  {t.content}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            className="input flex-1 min-w-0"
            placeholder="e.g. more conservative, add gold, focus on tax saving…"
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && chat.trim()) reviseMut.mutate(chat.trim()); }}
          />
          <button
            className="btn btn-primary"
            disabled={!chat.trim() || reviseMut.isPending}
            onClick={() => reviseMut.mutate(chat.trim())}
          >
            Update
          </button>
        </div>
      </div>

      <div className="flex flex-col items-center gap-3">
        <button
          className="btn btn-primary px-8 py-3 text-base rounded-xl"
          disabled={planMut.isPending}
          onClick={() => planMut.mutate()}
        >
          {planMut.isPending ? "Submitting…" : "Generate my plan →"}
        </button>
      </div>
    </div>
  );
}
