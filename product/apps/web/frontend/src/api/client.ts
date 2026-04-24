// Thin typed wrapper over fetch. All requests include cookies (session).
import type {
  PersonasResponse, PlanResponse,
  SessionSummary, StrategyResponse,
} from "./types";

const BASE = "/api/v2";

async function req<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const r = await fetch(BASE + path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  if (!r.ok) {
    let detail: string;
    try {
      detail = (await r.json()).detail ?? r.statusText;
    } catch {
      detail = r.statusText;
    }
    throw new ApiError(r.status, detail);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

// Session
export const getSession = () => req<SessionSummary>("GET", "/session");
export const setTier = (mode: "basic" | "premium") =>
  req<SessionSummary>("POST", "/session/tier", { mode });
export const submitProfile = (p: {
  name: string; age: number; monthly_sip_inr: number; existing_corpus_inr: number;
  risk_appetite: string; investment_horizon_years: number; life_stage: string;
  financial_goals: string[]; preferences?: string | null; tax_bracket?: string;
}) => req<SessionSummary>("POST", "/session/profile", p);
export const selectPersona = (persona_id: string) =>
  req<SessionSummary>("POST", "/session/persona", { persona_id });
export const resetSession = () => req<SessionSummary>("POST", "/session/reset");

export const requestOTP = (email: string) =>
  req<{ sent: boolean; message: string }>("POST", "/session/otp/request", { email });
export const verifyOTP = (email: string, code: string) =>
  req<{ verified: boolean; is_demo: boolean; message?: string }>(
    "POST", "/session/otp/verify", { email, code },
  );

// Personas
export const getPersonas = () => req<PersonasResponse>("GET", "/personas");

// Strategy
export const generateStrategy = () =>
  req<StrategyResponse>("POST", "/strategy/generate");
export const reviseStrategy = (feedback: string) =>
  req<StrategyResponse>("POST", "/strategy/revise", { feedback });
export const answerQuestions = (feedback: string) =>
  req<StrategyResponse>("POST", "/strategy/answer-questions", { feedback });

// Plan
export const generatePlan = () => req<{ ok: boolean }>("POST", "/plan/generate");
export const getPlan = () => req<PlanResponse>("GET", "/plan");

// CAS upload
export async function uploadCAS(file: File, password: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("password", password);
  const r = await fetch(BASE + "/profile/cas", {
    method: "POST",
    body: fd,
    credentials: "same-origin",
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<{
    holdings: Array<{ scheme: string; category: string; value_inr: number; units: number }>;
    total_value_inr: number;
    count: number;
  }>;
}

// Supporting documents (unified CAS + CIBIL + future)
export type StagedDoc = {
  doc_id: string;
  filename: string;
  size_bytes: number;
  requires_password: boolean;
  verified: boolean;
  detected_type: "cas" | "cibil" | "unknown";
};

export async function stageDocuments(files: File[]): Promise<{ documents: StagedDoc[]; errors: Array<{filename: string; error: string}> }> {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const r = await fetch(BASE + "/profile/documents", { method: "POST", body: fd, credentials: "same-origin" });
  if (!r.ok) throw new ApiError(r.status, r.statusText);
  return r.json();
}

export async function setDocumentPassword(docId: string, password: string): Promise<StagedDoc> {
  const r = await fetch(BASE + `/profile/documents/${docId}/password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
    credentials: "same-origin",
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json();
}

export async function removeDocument(docId: string): Promise<void> {
  const r = await fetch(BASE + `/profile/documents/${docId}`, { method: "DELETE", credentials: "same-origin" });
  if (!r.ok) throw new ApiError(r.status, r.statusText);
}

export async function extractDocuments(): Promise<{
  holdings_count: number;
  holdings_total_inr: number;
  credit_summary: null | {
    total_outstanding_inr: number;
    total_monthly_emi_inr: number;
    total_overdue_inr: number;
    active_account_count: number;
    closed_account_count: number;
    has_overdue: boolean;
  };
  skipped: Array<{ doc_id: string; filename: string; reason: string }>;
}> {
  const r = await fetch(BASE + "/profile/documents/extract", { method: "POST", credentials: "same-origin" });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json();
}
