import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import Agents from "../src/pages/Agents";
import Audit from "../src/pages/Audit";
import CRPage from "../src/pages/ChangeRequests";
import { Toaster, toast } from "../src/components/ui";
import { setToken } from "../src/services/api";

const EVENT = { seq: 3, ts: "2026-10-21T08:54:30.000Z", kind: "contract", agent_id: "proc-agent-07", verdict: "published",
  actor: "priya", tool: null, details: { version: 1, body_hash: "sha256:abc" },
  hash: "sha256:" + "b".repeat(64), prev_hash: "sha256:" + "a".repeat(64) };

const HEALTH = {
  status: "degraded", database: "ok", event_bus: "in-process",
  embeddings: { mode: "minilm-onnx", model: "all-MiniLM-L6-v2", error: null, load_ms: 600 },
  behavior_engine: { implemented: false, reason: "Behavior Engine not implemented" },
  policy_engine: { available: false, reason: "Trust Ladder policy engine not implemented" },
};
const AGENTS = [
  { id: "proc-agent-07", name: "Procurement-Agent-07", owner: "meera", role: "procurement", kind: "simulated", status: "active", contract_version: 1, canary: "CNRY-1234…", created_at: "2026-10-21T00:00:00" },
  { id: "support-agent-05", name: "Support-Agent-05", owner: "arjun", role: "support", kind: "simulated", status: "active", contract_version: 1, canary: "CNRY-9999…", created_at: "2026-10-21T00:00:00" },
];

function mockFetch(routes: Record<string, unknown>, status: Record<string, number> = {}) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = Object.keys(routes).find((p) => url.startsWith(p));
    const body = path ? routes[path] : { detail: "not found" };
    return new Response(JSON.stringify(body), { status: path ? status[path] ?? 200 : 404 });
  }));
}

afterEach(() => { vi.unstubAllGlobals(); setToken(null); });

describe("TETHER console", () => {
  it("shows the login screen when there is no session", async () => {
    mockFetch({ "/v1/auth/me": { detail: "login required" } }, { "/v1/auth/me": 401 });
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByText("TETHER Console")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
  });

  it("shows a login error from the API", async () => {
    mockFetch({ "/v1/auth/me": {}, "/v1/auth/login": { detail: "invalid credentials" } }, { "/v1/auth/me": 401, "/v1/auth/login": 401 });
    render(<MemoryRouter><App /></MemoryRouter>);
    fireEvent.change(await screen.findByLabelText("Password"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("invalid credentials");
  });

  it("overview states plainly that enforcement is degraded", async () => {
    mockFetch({ "/v1/auth/me": { username: "priya", display: "Priya", roles: ["security", "viewer"] }, "/v1/health": HEALTH,
      "/v1/agents": AGENTS, "/v1/change-requests": [], "/v1/audit/verify": { valid: true, checked: 9 },
      "/v1/audit/events": [EVENT] });
    setToken("test-session"); // an existing session triggers the /auth/me probe
    render(<MemoryRouter><App /></MemoryRouter>);
    expect(await screen.findByText("The seven pillars in this build")).toBeInTheDocument();
    expect(screen.getByText("Not in this build")).toBeInTheDocument();
    expect(screen.getAllByText("not implemented")).toHaveLength(2);
    expect(await screen.findByText("Verified")).toBeInTheDocument();
    expect(await screen.findByText("Contract v1 published for proc-agent-07")).toBeInTheDocument();
    expect(await screen.findByText(/enforcement fail-closed/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /constellation/i })).toBeInTheDocument();
    expect(document.title).toBe("Overview · TETHER");
  });

  it("audit rows expand to show details and the hash link", async () => {
    mockFetch({ "/v1/audit/events": [EVENT] });
    render(<MemoryRouter><Audit /></MemoryRouter>);
    const row = await screen.findByText("published");
    fireEvent.click(row);
    expect(await screen.findByText(EVENT.prev_hash)).toBeInTheDocument();
    expect(screen.getByText(/"body_hash"/)).toBeInTheDocument();
  });

  it("hides the change-request form from non-owners", async () => {
    mockFetch({ "/v1/change-requests": [], "/v1/agents": AGENTS });
    render(<MemoryRouter><CRPage /></MemoryRouter>);
    expect(await screen.findByText(/Only agent owners can submit/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sign and submit/ })).not.toBeInTheDocument();
  });

  it("toasts render and auto-dismiss", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<Toaster />);
    act(() => toast.err("requester is not the owner of this agent"));
    expect(await screen.findByText("requester is not the owner of this agent")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(5100); });
    await waitFor(() => expect(screen.queryByText("requester is not the owner of this agent")).not.toBeInTheDocument());
    vi.useRealTimers();
  });

  it("filters agents by search text and role", async () => {
    mockFetch({ "/v1/agents": AGENTS });
    render(<MemoryRouter><Agents /></MemoryRouter>);
    expect(await screen.findByText("Procurement-Agent-07")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter by role"), { target: { value: "support" } });
    await waitFor(() => expect(screen.queryByText("Procurement-Agent-07")).not.toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Search agents"), { target: { value: "zzz" } });
    expect(await screen.findByText("No agents match.")).toBeInTheDocument();
  });

  it("surfaces API errors instead of blank pages", async () => {
    mockFetch({ "/v1/agents": { detail: "boom" } }, { "/v1/agents": 500 });
    render(<MemoryRouter><Agents /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
  });
});
