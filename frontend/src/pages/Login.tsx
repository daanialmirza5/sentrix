import { useState } from "react";
import { FileSignature, KeyRound, ScanSearch } from "lucide-react";
import { post, type User } from "../services/api";
import { TetherMark, useAuth } from "../App";
import { Button, ErrorBox, Spinner, useTitle } from "../components/ui";
import Constellation3D from "../components/LazyConstellation";

const PERSONAS = [
  { u: "priya", d: "Priya: SOC analyst, security approver" },
  { u: "meera", d: "Meera: agent owner" },
  { u: "arjun", d: "Arjun: platform engineer (admin)" },
  { u: "auditor", d: "Auditor: read-only compliance" },
];
// Decorative backdrop only (no data claims): one node per role colour.
const BACKDROP = ["procurement", "orchestrator", "support", "procurement", "hr", "support", "procurement"]
  .map((role, i) => ({ id: `bg-${i}`, label: "", role, version: 1 }));
const POINTS = [
  { icon: FileSignature, t: "Signed Role Contracts", d: "Owner + security signatures; changes only through approved requests." },
  { icon: KeyRound, t: "Task-bound credentials", d: "Each task gets the narrowest scope, a short TTL and cascading revocation." },
  { icon: ScanSearch, t: "Causal blame", d: "Out-of-role actions are traced back to the untrusted line that caused them." },
];

export default function Login() {
  useTitle("Sign in");
  const { signIn } = useAuth();
  const [username, setUsername] = useState("priya");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await post<{ token: string; user: User }>("/v1/auth/login", { username, password });
      signIn(r.token, r.user);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  return (
    <div className="relative min-h-screen overflow-hidden font-sans">
      <div className="pointer-events-none absolute inset-y-0 right-0 w-full lg:w-[70%]" data-testid="login-backdrop">
        <Constellation3D nodes={BACKDROP} height={typeof window !== "undefined" ? window.innerHeight : 800} decorative />
      </div>
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-ink-950 via-ink-950/75 to-ink-950/10" />
      <div className="relative mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-6 py-10 lg:grid-cols-[1.2fr_1fr]">
        <div className="animate-rise">
          <div className="flex items-center gap-3"><TetherMark className="h-11 w-11" />
            <span className="font-display text-2xl font-bold tracking-[0.2em] text-ink-100">TETHER</span></div>
          <h1 className="mt-8 font-display text-4xl leading-tight font-bold text-ink-100 md:text-5xl">
            Valid token ≠<br /><span className="text-gradient">valid behavior.</span></h1>
          <p className="mt-4 max-w-lg text-ink-300">Role-anchored identity drift detection for autonomous AI agents.
            IAM asks “is this allowed?”. TETHER asks “is this still you?”</p>
          <ul className="mt-8 hidden space-y-4 md:block">
            {POINTS.map(({ icon: Icon, t, d }) => (
              <li key={t} className="flex gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-cyan-400/20 bg-cyan-400/10"><Icon className="h-4 w-4 text-cyan-300" /></span>
                <div><div className="text-sm font-semibold text-ink-100">{t}</div><div className="text-sm text-ink-500">{d}</div></div>
              </li>))}
          </ul>
        </div>
        <form onSubmit={submit} className="glass w-full animate-rise space-y-4 rounded-2xl p-7 [animation-delay:120ms]">
          <div>
            <h2 className="font-display text-xl font-semibold text-ink-100">TETHER Console</h2>
            <p className="mt-1 text-sm text-ink-500">Sign in as one of the demo personas from the PRD.</p>
          </div>
          <label className="block text-xs font-medium text-ink-300">Persona
            <select className="mt-1.5 w-full" value={username} onChange={(e) => setUsername(e.target.value)} aria-label="Persona">
              {PERSONAS.map((p) => <option key={p.u} value={p.u}>{p.d}</option>)}
            </select>
          </label>
          <label className="block text-xs font-medium text-ink-300">Password
            <input className="mt-1.5 w-full" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} aria-label="Password" />
          </label>
          {error && <ErrorBox message={error} />}
          <Button type="submit" disabled={busy || !password} className="w-full py-2.5">{busy && <Spinner />}Sign in</Button>
          <p className="text-center text-[11px] text-ink-500">Demo authentication · password set by TETHER_DEMO_PASSWORD (see README)</p>
        </form>
      </div>
    </div>
  );
}
