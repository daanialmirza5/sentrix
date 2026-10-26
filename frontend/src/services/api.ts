// Thin typed client over the SENTRIX REST API. The operator token lives in memory + sessionStorage.
export type User = { username: string; display: string; roles: string[] };

let token: string | null = null;
try { token = sessionStorage.getItem("sentrix.token"); } catch { token = null; }

export const hasToken = () => !!token;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function setToken(t: string | null) {
  token = t;
  try { if (t) sessionStorage.setItem("sentrix.token", t); else sessionStorage.removeItem("sentrix.token"); } catch { /* storage unavailable */ }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  const text = await res.text();
  let body: unknown = text;
  try { body = text ? JSON.parse(text) : null; } catch { /* plain text */ }
  if (!res.ok) {
    const detail = (body as { detail?: unknown })?.detail;
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail ?? body));
  }
  return body as T;
}

export const post = <T,>(path: string, data: unknown) => api<T>(path, { method: "POST", body: JSON.stringify(data) });

export type Health = {
  status: string; database: string; event_bus: string;
  embeddings: { mode: string; model: string; error: string | null; load_ms: number | null };
  behavior_engine: { implemented: boolean; reason: string };
  policy_engine: { available: boolean; reason: string };
};
export type Agent = { id: string; name: string; owner: string; role: string; kind: string; status: string;
  contract_version: number | null; canary: string; created_at: string };
export type Verification = { valid: boolean; body_hash_ok: boolean; signatures: { identity: string; role: string; valid: boolean; signed_at: string }[] };
export type ContractVersion = { version: number; status: string; body: Record<string, unknown>; body_hash: string;
  verification: Verification; change_request_id: string | null; created_by: string; created_at: string };
export type ChangeRequest = { id: string; agent_id: string; base_version: number; changes: Record<string, string[]>;
  justification: string; requester: string; status: string; approver: string | null; resulting_version: number | null;
  decision_note: string | null; requester_signed: boolean; approver_signed: boolean; created_at: string };
export type AuditEvent = { seq: number; ts: string; kind: string; agent_id: string | null; verdict: string | null;
  actor: string | null; tool: string | null; details: Record<string, unknown>; hash: string; prev_hash: string };
export type TokenRow = { jti: string; agent_id: string; task_id: string; session_id: string; parent_jti: string | null;
  scope: string[]; depth: number; contract_version: number; issued_at: number; expires_at: number;
  status: "active" | "expired" | "revoked"; revoked_reason: string | null };
export type Signals = { R: number; B: number; P: number; S: number };
export type Analysis = {
  analysis_only: true; risk: number; risk_raw: number; override: "deception" | "drift" | null; would_hard_deny: boolean;
  signals: Signals; contributions: Signals; disabled_signals: string[]; note: string;
  action: { verb: string; resource: string | null; tool: string; action_type: string; destination: string | null; bytes_out: number; sensitivity: number; text: string };
  role_fit: { s_r: number; rules: { rule: string; score: number; detail: string }[]; hard_deny: string[]; fit: number | null; nearest_anchor: string | null; semantic_score: number | null; mode: string };
  deception: { honey: string | null; canaries: { masked: string; owner: string | null }[]; dlp: string[] };
  provenance: { s_p: number; tau: number | null; source: string | null; steps_since: number | null;
    attribution: { source: string; confidence: number; uncertain: boolean; span: { page: number; line: number; text: string; patterns: string[] } | null } | null };
  explanation: { why: string; factors: string; cause: string | null };
};
export type DriftPoint = { window: number; phase: "benign" | "drift"; S: number; S_rolling: number };
export type DriftSummary = { benign_false_alarm_rate: number; detection_rate: number; median_delay_windows: number | null };
export type DriftReport = { description: string; k: number; calibrated_h: number; calibration_seeds: number[]; held_out_seeds: number[];
  calibration_default_h5: Record<"frozen" | "rolling", DriftSummary>; held_out_default_h5: Record<"frozen" | "rolling", DriftSummary>;
  held_out_calibrated: Record<"frozen" | "rolling", DriftSummary> & { n: number };
  trace: { seed: number; h: number; drift_starts_after_window: number; points: DriftPoint[] } };
export type ChainCheck = { valid: boolean; checked: number; total_events?: number; head?: string; broken_at_seq?: number; reason?: string };
