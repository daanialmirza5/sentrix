import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Bot, FileCheck2, FlaskConical, GitPullRequest, KeyRound, LayoutDashboard, LogOut, ScrollText, TrendingUp } from "lucide-react";
import Credentials from "./pages/Credentials";
import SignalLab from "./pages/SignalLab";
import Drift from "./pages/Drift";
import { api, hasToken, setToken, type Health, type User } from "./services/api";
import { Badge, Toaster, useApi } from "./components/ui";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Agents from "./pages/Agents";
import Contracts from "./pages/Contracts";
import ChangeRequests from "./pages/ChangeRequests";
import Audit from "./pages/Audit";

type AuthCtx = { user: User | null; signIn: (t: string, u: User) => void; signOut: () => void };
const Auth = createContext<AuthCtx>({ user: null, signIn: () => {}, signOut: () => {} });
export const useAuth = () => useContext(Auth);

const NAV_GROUPS = [
  { title: "Monitor", items: [
    { to: "/", label: "Overview", icon: LayoutDashboard },
    { to: "/agents", label: "Agents", icon: Bot },
    { to: "/drift", label: "Drift", icon: TrendingUp },
  ] },
  { title: "Govern", items: [
    { to: "/contracts", label: "Role Contracts", icon: FileCheck2 },
    { to: "/change-requests", label: "Change Requests", icon: GitPullRequest },
    { to: "/credentials", label: "Credentials", icon: KeyRound },
  ] },
  { title: "Investigate", items: [
    { to: "/signal-lab", label: "Signal Lab", icon: FlaskConical },
    { to: "/audit", label: "Audit Log", icon: ScrollText },
  ] },
];
const NAV = NAV_GROUPS.flatMap((g) => g.items);

/** Brand mark: a core with an orbiting, tethered node. */
export function TetherMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <defs><linearGradient id="tm" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#67e8f9" /><stop offset="1" stopColor="#a78bfa" /></linearGradient></defs>
      <circle cx="16" cy="16" r="13" fill="none" stroke="url(#tm)" strokeOpacity=".45" strokeWidth="1.2" />
      <line x1="16" y1="16" x2="25.2" y2="6.8" stroke="url(#tm)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="16" cy="16" r="5" fill="url(#tm)" />
      <circle cx="25.2" cy="6.8" r="2.6" fill="#e8eef8" />
    </svg>
  );
}
export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);
  useEffect(() => {
    if (!hasToken()) { setChecked(true); return; } // no session: skip the probe (avoids a 401 on every visit)
    api<User>("/v1/auth/me").then(setUser).catch(() => setToken(null)).finally(() => setChecked(true));
  }, []);
  const ctx: AuthCtx = {
    user,
    signIn: (t, u) => { setToken(t); setUser(u); },
    signOut: () => { setToken(null); setUser(null); },
  };
  if (!checked) return null;
  return (
    <Auth.Provider value={ctx}>
      {!user ? <Login /> : (
        <div className="flex min-h-screen font-sans text-ink-100">
          <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950/60 backdrop-blur-xl md:flex">
            <div className="flex items-center gap-3 px-5 pt-6 pb-5">
              <TetherMark className="h-9 w-9" />
              <div>
                <div className="font-display text-lg font-bold tracking-[0.18em]">TETHER</div>
                <div className="text-[11px] text-ink-500">Valid token ≠ valid behavior</div>
              </div>
            </div>
            <nav className="flex-1 space-y-5 overflow-y-auto px-3 pt-2" aria-label="Main">
              {NAV_GROUPS.map((g) => (
                <div key={g.title}>
                  <div className="px-3 pb-1.5 text-[10px] font-semibold tracking-[0.2em] text-ink-500 uppercase">{g.title}</div>
                  <div className="space-y-0.5">
                    {g.items.map(({ to, label, icon: Icon }) => (
                      <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) =>
                        `group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${isActive
                          ? "bg-gradient-to-r from-cyan-400/15 to-violet-400/5 text-ink-100"
                          : "text-ink-300 hover:bg-white/[0.04] hover:text-ink-100"}`}>
                        {({ isActive }) => (<>
                          {isActive && <span className="absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full bg-gradient-to-b from-cyan-300 to-violet-400" />}
                          <Icon className={`h-4 w-4 ${isActive ? "text-cyan-300" : "text-ink-500 group-hover:text-ink-300"}`} />{label}
                        </>)}
                      </NavLink>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
            <div className="m-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-cyan-400 to-violet-500 font-display text-sm font-bold text-ink-950">
                  {user.username.slice(0, 1).toUpperCase()}</div>
                <div className="min-w-0">
                  <div className="truncate text-sm text-ink-100">{user.display.split(" (")[0]}</div>
                  <div className="truncate text-[11px] text-ink-500">{user.roles.filter((r) => r !== "viewer").join(" · ") || "read-only"}</div>
                </div>
              </div>
              <button onClick={ctx.signOut} className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-white/[0.06] py-1.5 text-xs text-ink-300 transition hover:bg-white/[0.05] hover:text-ink-100"><LogOut className="h-3.5 w-3.5" />Sign out</button>
            </div>
          </aside>
          <div className="flex min-w-0 flex-1 flex-col">
            <StatusBar user={user} onSignOut={ctx.signOut} />
            <nav className="flex gap-1 overflow-x-auto border-b border-white/[0.06] bg-ink-950/70 px-3 py-2 backdrop-blur md:hidden" aria-label="Mobile">
              {NAV.map(({ to, label }) => <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) =>
                `whitespace-nowrap rounded-full px-3 py-1 text-xs ${isActive ? "bg-cyan-400/15 text-cyan-200" : "text-ink-300"}`}>{label}</NavLink>)}
            </nav>
            <main className="mx-auto w-full max-w-[1400px] flex-1 p-4 md:p-8">
              <Routes>
                <Route path="/" element={<Overview />} />
                <Route path="/agents" element={<Agents />} />
                <Route path="/contracts" element={<Contracts />} />
                <Route path="/contracts/:agentId" element={<Contracts />} />
                <Route path="/change-requests" element={<ChangeRequests />} />
                <Route path="/credentials" element={<Credentials />} />
                <Route path="/signal-lab" element={<SignalLab />} />
                <Route path="/drift" element={<Drift />} />
                <Route path="/audit" element={<Audit />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </main>
          </div>
        </div>
      )}
      <Toaster />
    </Auth.Provider>
  );
}

/** Live system state, refreshed every 30 s, visible on every page. */
function StatusBar({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const { data, error, reload } = useApi<Health>("/v1/health");
  useEffect(() => { const t = setInterval(reload, 30000); return () => clearInterval(t); }, [reload]);
  const state = error ? { tone: "bad" as const, text: "API unreachable" }
    : !data ? { tone: "muted" as const, text: "checking…" }
    : data.policy_engine.available ? { tone: "ok" as const, text: "Enforcing" }
    : { tone: "info" as const, text: "Detection & governance online · enforcement fail-closed" };
  return (
    <header className="sticky top-0 z-30 flex items-center justify-between gap-3 border-b border-white/[0.06] bg-ink-950/70 px-4 py-2.5 backdrop-blur-xl md:px-8">
      <div className="flex min-w-0 items-center gap-3 text-xs text-ink-500">
        <TetherMark className="h-6 w-6 md:hidden" />
        <Badge tone={state.tone}><span className={`h-1.5 w-1.5 rounded-full ${state.tone === "bad" ? "bg-rose-400" : state.tone === "muted" ? "bg-ink-500" : "animate-pulse-ring bg-cyan-300"}`} />
          <span className="truncate">{state.text}</span></Badge>
        {data && <span className="hidden items-center gap-1.5 font-mono lg:flex"><span className={`h-1.5 w-1.5 rounded-full ${data.embeddings.mode === "minilm-onnx" ? "bg-emerald-400" : "bg-ink-500"}`} />MiniLM: {data.embeddings.mode === "uninitialised" ? "loads on first use" : data.embeddings.mode}</span>}
      </div>
      <div className="flex items-center gap-3 text-xs md:hidden">
        <span className="text-ink-300">{user.username}</span>
        <button onClick={onSignOut} aria-label="Log off" className="text-ink-500 hover:text-ink-100"><LogOut className="h-4 w-4" /></button>
      </div>
    </header>
  );
}
