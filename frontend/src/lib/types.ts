// lib/types.ts

export interface Stats {
  avg_score:   number
  pass_rate:   number
  total_calls: number
  cost:        number
}

export interface MetricPoint {
  hour:       string
  avg_score:  number
  call_count: number
}

export interface Alert {
  id:       string
  type:     string
  severity: "low" | "medium" | "high" | "critical"
  message:  string
}

export interface EvalRun {
  run_id:     string
  name:       string
  pass_rate:  number
  avg_score:  number
  status:     "pending" | "running" | "completed" | "failed"
  total:      number
  passed:     number
  failed:     number
  created_at: string
  results?:   EvalResult[]
}

export interface EvalResult {
  input:     string
  score:     number
  passed:    boolean
  reasoning: string
  category?: string
}

export interface Span {
  id:          string
  span_id?:    string
  trace_id:    string
  name:        string
  score:       number | null
  status:      string
  duration_ms: number
  timestamp:   number
  input:       string
  output:      string
  has_error:   boolean
}

export interface Dataset {
  id:            string
  name:          string
  description:   string
  example_count: number
  created_at:    string
}

export interface Example {
  input:    string
  expected: string
  criteria: string[]
  category: string
}

export interface HallucinationClaim {
  text:       string
  type:       string
  risk_level: string
  evidence?:  string
}

export interface HallucinationResult {
  overall_risk:        string
  hallucination_score: number
  total_claims:        number
  summary:             string
  analysis_time_ms:    number
  claims:              HallucinationClaim[]
}

export interface ABResult {
  winner:           string
  is_significant:   boolean
  is_improvement:   boolean
  recommendation:   string
  p_value:          number
  effect_size_label: string
  score_delta:      number
  variant_a:        { pass_rate: number; avg_score: number }
  variant_b:        { pass_rate: number; avg_score: number }
}

// ─── Score helpers (defined once, imported everywhere) ────────────────────────
export const scoreColor = (v: number | null): string =>
  v === null ? "var(--t3)" : v >= 8 ? "var(--p0)" : v >= 6 ? "var(--a0)" : "var(--r0)"

export const scoreChip = (v: number | null): string =>
  v === null ? "sig-x" : v >= 8 ? "sig-p" : v >= 6 ? "sig-a" : "sig-r"

export const statusChip = (s: string): string =>
  s === "completed" ? "sig-p" : s === "running" ? "sig-c" : "sig-r"

export const riskColor = (r: string): string =>
  ({ low: "var(--p0)", medium: "var(--a0)", high: "var(--a0)", critical: "var(--r0)" }[r] ?? "var(--t2)")

export const riskBg = (r: string): string =>
  ({ low: "var(--pg)", medium: "var(--ag)", high: "var(--ag)", critical: "var(--rg)" }[r] ?? "var(--raised)")

export const riskBorder = (r: string): string =>
  ({ low: "var(--pb)", medium: "var(--ab)", high: "var(--ab)", critical: "var(--rb)" }[r] ?? "var(--b2)")

export const typeColor = (t: string): string =>
  ({ none: "var(--p0)", factual: "var(--r0)", fabrication: "var(--a0)", contradiction: "var(--c0)", overconfident: "var(--a0)" }[t] ?? "var(--t2)")