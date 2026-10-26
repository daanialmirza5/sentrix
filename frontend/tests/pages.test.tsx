import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import SignalLab from "../src/pages/SignalLab";
import Drift from "../src/pages/Drift";
import Credentials from "../src/pages/Credentials";

const AGENTS = [{ id: "proc-agent-07", name: "P", owner: "meera", role: "procurement", kind: "simulated", status: "active", contract_version: 1, canary: "CNRY-1…", created_at: "2026-10-21T00:00:00" }];
const ANALYSIS = {
  analysis_only: true, risk: 95, risk_raw: 83.7, override: "deception", would_hard_deny: true,
  signals: { R: 1, B: 0, P: 0.82, S: 0.475 }, contributions: { R: 44.1, B: 0, P: 37.4, S: 18.5 }, disabled_signals: ["B"],
  note: "Analysis only.", action: { verb: "read", resource: "/hr/salary_backup.xlsx", tool: "fs.read", action_type: "data_read", destination: null, bytes_out: 0, sensitivity: 0.95, text: "read fs read hr salary backup xlsx" },
  role_fit: { s_r: 1, rules: [{ rule: "deny_domain", score: 1, detail: "matches deny-list 'hr/*'" }], hard_deny: ["deny_domain"], fit: 0.23, nearest_anchor: "retrieve supplier price quotes", semantic_score: 0.79, mode: "minilm-onnx" },
  deception: { honey: "hr/salary_backup.xlsx", canaries: [], dlp: [] },
  provenance: { s_p: 0.82, tau: 0.82, source: "supplier_quote.pdf", steps_since: 1, attribution: { source: "supplier_quote.pdf", confidence: 0.9, uncertain: false, span: { page: 2, line: 14, text: "[[SENTRIX-TEST-INJECTION: ...]]", patterns: [] } } },
  explanation: { why: "read /hr/salary_backup.xlsx.", factors: "Deception override", cause: "supplier_quote.pdf, page 2, line 14" },
};
const pts = Array.from({ length: 60 }, (_, i) => ({ window: i + 1, phase: i < 40 ? "benign" : "drift", S: i < 40 ? 0 : (i - 39) * 2, S_rolling: i < 40 ? 0 : (i - 39) * 0.8 }));
const SUM = { frozen: { benign_false_alarm_rate: 0.067, detection_rate: 1, median_delay_windows: 13 }, rolling: { benign_false_alarm_rate: 0.067, detection_rate: 1, median_delay_windows: 17.5 } };
const DRIFT = { description: "Synthetic.", k: 0.5, calibrated_h: 10, calibration_seeds: [0], held_out_seeds: [10], calibration_default_h5: SUM,
  held_out_default_h5: SUM, held_out_calibrated: { ...SUM, n: 30 }, trace: { seed: 10, h: 10, drift_starts_after_window: 40, points: pts } };

function mockFetch(routes: Record<string, unknown>) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => {
    const path = Object.keys(routes).find((p) => url.startsWith(p));
    return new Response(JSON.stringify(path ? routes[path] : { detail: "nf" }), { status: path ? 200 : 404 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
afterEach(() => vi.unstubAllGlobals());

describe("new pages", () => {
  it("Signal Lab sends the preset and renders the explained result", async () => {
    const fetch = mockFetch({ "/v1/agents": AGENTS, "/v1/analyze": ANALYSIS });
    render(<MemoryRouter><SignalLab /></MemoryRouter>);
    fireEvent.click(await screen.findByText("Out-of-role read 1 step after poisoned quote"));
    fireEvent.click(screen.getByRole("button", { name: /Analyse/ }));
    expect(await screen.findByText("95.0")).toBeInTheDocument();
    expect(screen.getByText(/Cause: supplier_quote.pdf, page 2, line 14/)).toBeInTheDocument();
    expect(screen.getByText(/disabled, not implemented/)).toBeInTheDocument();
    const call = fetch.mock.calls.find(([u]) => String(u) === "/v1/analyze")!;
    const sent = JSON.parse(String((call[1] as RequestInit).body));
    expect(sent).toMatchObject({ tool: "fs.read", steps_since_untrusted: 1, fixture: "poisoned_quote" });
  });

  it("Signal Lab reports invalid JSON args without calling the API", async () => {
    const fetch = mockFetch({ "/v1/agents": AGENTS });
    render(<MemoryRouter><SignalLab /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText(/Arguments/), { target: { value: "{bad" } });
    fireEvent.click(screen.getByRole("button", { name: /Analyse/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not valid JSON");
    expect(fetch.mock.calls.some(([u]) => String(u) === "/v1/analyze")).toBe(false);
  });

  it("Drift renders the chart, legend and data-driven reading", async () => {
    mockFetch({ "/v1/reports/drift": DRIFT });
    render(<MemoryRouter><Drift /></MemoryRouter>);
    expect(await screen.findByRole("img", { name: /CUSUM statistic/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Legend")).toHaveTextContent("Rolling baseline");
    expect(screen.getByText(/median delay is 13 windows/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Full run" }));
    expect(screen.getByRole("button", { name: "Full run" })).toHaveAttribute("aria-pressed", "true");
  });

  it("Credentials hides revoke without the security role", async () => {
    mockFetch({ "/v1/tokens": [{ jti: "tk-1", agent_id: "a", task_id: "t", session_id: "s", parent_jti: null, scope: ["x.y"], depth: 0,
      contract_version: 1, issued_at: 1, expires_at: 9999999999, status: "active", revoked_reason: null }] });
    render(<MemoryRouter><Credentials /></MemoryRouter>);
    expect(await screen.findByText("tk-1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Revoke/ })).not.toBeInTheDocument();
    expect(screen.getByText(/requires the security role/)).toBeInTheDocument();
  });
});
