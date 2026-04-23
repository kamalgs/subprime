// Mirrors product/apps/web/api_v2/dto.py + core/models.py.
// Can later be auto-generated via openapi-typescript.

export type Mode = "basic" | "premium";
export type Risk = "conservative" | "moderate" | "aggressive";

export interface SessionSummary {
  id: string;
  current_step: number;
  mode: Mode;
  is_demo: boolean;
  has_profile: boolean;
  has_strategy: boolean;
  has_plan: boolean;
  plan_generating: boolean;
  plan_error: string | null;
}

export interface Archetype {
  id: string;
  name: string;
  blurb: string;
  age: number;
  life_stage: string;
  risk_appetite: Risk;
  investment_horizon_years: number;
  monthly_sip_inr: number;
  existing_corpus_inr: number;
  financial_goals: string[];
}

export interface PersonaSummary {
  id: string;
  name: string;
  age: number;
  risk_appetite: string;
  investment_horizon_years: number;
  monthly_investible_surplus_inr: number;
  financial_goals: string[];
}

export interface PersonasResponse {
  archetypes: Archetype[];
  personas: PersonaSummary[] | null;
}

export interface StrategyOutline {
  equity_pct: number;
  debt_pct: number;
  gold_pct: number;
  other_pct: number;
  equity_sub: Record<string, number>;
  debt_sub: Record<string, number>;
  equity_approach: string;
  key_themes: string[];
  risk_return_summary: string;
  open_questions: string[];
}

export interface ChatTurn {
  role: "user" | "advisor";
  content: string;
}

export interface StrategyResponse {
  strategy: StrategyOutline;
  chat: ChatTurn[];
}

export interface Fund {
  amfi_code: string;
  name: string;
  display_name?: string;  // short UI-friendly label; falls back to name
  category: string;
  sub_category: string;
  fund_house: string;
  expense_ratio: number;
  morningstar_rating: number | null;
  returns_1y: number | null;
  returns_3y: number | null;
  returns_5y: number | null;
}

export interface Allocation {
  fund: Fund;
  allocation_pct: number;
  mode: "sip" | "lumpsum" | "both";
  monthly_sip_inr: number | null;
  lumpsum_inr: number | null;
  rationale: string;
}

export interface Plan {
  allocations: Allocation[];
  setup_phase: string;
  review_checkpoints: string[];
  rebalancing_guidelines: string;
  projected_returns: { bear?: number; base?: number; bull?: number };
  rationale: string;
  risks: string[];
  disclaimer: string;
}

export interface InvestorProfile {
  id: string;
  name: string;
  age: number;
  risk_appetite: Risk;
  investment_horizon_years: number;
  monthly_investible_surplus_inr: number;
  existing_corpus_inr: number;
  financial_goals: string[];
  life_stage: string;
  tax_bracket: string;
  preferences: string | null;
}

export interface PlanResponse {
  plan: Plan;
  profile: InvestorProfile;
  strategy: StrategyOutline | null;
}

export interface PlanStatus {
  ready: boolean;
  generating: boolean;
  error: string | null;
  stages_done?: string[];
  stages_planned?: string[];
}
