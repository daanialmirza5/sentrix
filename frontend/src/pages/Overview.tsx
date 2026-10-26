import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Bot, FileSignature, FlaskConical, GitPullRequest, Link2, ShieldCheck } from "lucide-react";
import type { Agent, AuditEvent, ChainCheck, ChangeRequest, Health } from "../services/api";
import { Badge, Card, Empty, ErrorBox, Loading, PageHeader, Stat, type Tone, useApi } from "../components/ui";
import Constellation3D from "../components/LazyConstellation";

const DOT: Record<string, string> = { contract: "bg-emerald-400", change_request: "bg-cyan-300", token: "bg-violet-400",
  gateway: "bg-rose-400", admin: "bg-amber-300" };

function describe(e: AuditEvent): string {
  const who = e.agent_id ?? "system";
  const d = e.details as Record<string, unknown>;
  switch (e.kind) {
    case "contract": return `Contract v${d.version} published for ${who}`;
    case "change_request": return `Change request ${d.change_request} ${e.verdict} for ${who}`;
    case "token": return `Task token ${e.verdict} for ${who}`;
    case "gateway": return `Gateway refused ${e.tool ?? "call"} from ${who} (fail-closed)`;
    case "admin": return `${String(e.verdict).replace("_", " ")}: ${who}`;
    default: return `${e.kind} ${e.verdict ?? ""}`;
  }
}

/** PRD §4 pillars and their actual state in this build. Kept accurate for evaluation. */
const PILLARS: { n: string; name: string; what: string; state: string; tone: Tone; to?: string }[] = [
  { n: "1", name: "Role Contract + Role-Fit", what: "Ed25519-signed contracts; deterministic rules + MiniLM similarity", state: "Live", tone: "ok", to: "/contracts" },
  { n: "2", name: "Task-Bound Credentials", what: "Scope = contract ∩ task ∩ parent; TTL; cascading revocation", state: "Live", tone: "ok", to: "/credentials" },
  { n: "3", name: "Causal Provenance", what: "Taint windows and span attribution to the source line", state: "Analysis", tone: "info", to: "/signal-lab" },
  { n: "4", name: "Deception Layer", what: "Honey-resources, per-agent canaries, egress DLP", state: "Analysis", tone: "info", to: "/signal-lab" },
  { n: "5", name: "Canary-Instruction Heartbeat", what: "Injection Susceptibility Index (Beta posterior)", state: "Engine", tone: "violet" },
  { n: "6", name: "Frozen Anchor + CUSUM", what: "Signed anchor, measured on held-out seeds; signed change requests", state: "Measured", tone: "info", to: "/drift" },
  { n: "7", name: "Delegation Graph", what: "Authority attenuation via token scope; cascade on revoke", state: "Partial", tone: "warn", to: "/credentials" },
];

export default function Overview() {
  const nav = useNavigate();
  const health = useApi<Health>("/v1/health");
  const agents = useApi<Agent[]>("/v1/agents");
  const crs = useApi<ChangeRequest[]>("/v1/change-requests");
  const chain = useApi<ChainCheck>("/v1/audit/verify");
  const recent = useApi<AuditEvent[]>("/v1/audit/events?limit=8");
  const nodes = useMemo(() => (agents.data ?? []).filter((a) => a.status === "active")
    .map((a) => ({ id: a.id, label: a.name, role: a.role, version: a.contract_version })), [agents.data]);

  if (health.loading || agents.loading) return <Loading rows={6} />;
  if (health.error) return <ErrorBox message={`Backend unreachable: ${health.error}`} />;
  const h = health.data!;
  const signed = (agents.data ?? []).filter((a) => a.contract_version).length;
  const pending = (crs.data ?? []).filter((c) => c.status === "pending").length;

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Command centre" title="Overview" subtitle="Live state of the agent fleet from the SENTRIX API. All agents and data are synthetic." />
      {/* Hero */}
      <section className="glass relative overflow-hidden rounded-3xl">
        <div className="grid-bg pointer-events-none absolute inset-0" />
        <div className="relative grid items-center gap-2 lg:grid-cols-[1.3fr_1fr]">
          <div className="animate-rise p-7 md:p-10">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold tracking-[0.18em] text-cyan-200 uppercase">
              Identity drift detection · AI agents</div>
            <h2 className="font-display text-3xl leading-[1.1] font-bold xl:text-[40px]">
              IAM asks <span className="text-ink-300">“is this allowed?”</span><br /><span className="text-gradient">SENTRIX asks “is this still you?”</span>
            </h2>
            <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-ink-300">
              Every agent is bound to a signed Role Contract and watched on every action. Its behaviour is scored against role, task and provenance,
              so a hijacked agent with a perfectly valid token stands out.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link to="/signal-lab" className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-400 to-violet-400 px-4 py-2.5 text-sm font-semibold text-ink-950 shadow-[0_8px_30px_-8px_rgb(34_211_238/.7)] transition hover:brightness-110">
                <FlaskConical className="h-4 w-4" />Open Signal Lab</Link>
              <Link to="/contracts" className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-semibold text-ink-100 transition hover:bg-white/[0.07]">
                View Role Contracts<ArrowRight className="h-4 w-4" /></Link>
            </div>
          </div>
          <div className="relative pb-4">
            <Constellation3D nodes={nodes} height={380} onSelect={(id) => nav(`/contracts/${id}`)} />
            <div className="mx-auto w-fit rounded-full border border-white/[0.08] bg-ink-950/70 px-3 py-1 text-[11px] text-ink-300 backdrop-blur">
              <span className="font-semibold text-cyan-300">{nodes.length}</span> agents under watch at the gateway · hover to inspect · click to open the contract</div>
          </div>
        </div>
      </section>

      {/* KPIs */}
      <div className="stagger grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat icon={<Bot className="h-3.5 w-3.5" />} label="Registered agents" value={agents.data?.length ?? 0} hint="synthetic fleet" />
        <Stat icon={<FileSignature className="h-3.5 w-3.5" />} label="Signed contracts" value={signed} hint="owner + security signatures" accent="violet" />
        <Stat icon={<GitPullRequest className="h-3.5 w-3.5" />} label="Pending changes" value={pending} hint="awaiting security approval" accent="amber" />
        <Stat icon={<Link2 className="h-3.5 w-3.5" />} label="Audit chain" accent="emerald"
          value={chain.data ? (chain.data.valid ? <span className="flex items-center gap-2"><ShieldCheck className="h-7 w-7 text-emerald-300" />Verified</span> : "Broken") : "…"}
          hint={chain.data ? `${chain.data.checked} hash-linked events` : undefined} />
      </div>

      {/* Pillars */}
      <Card title="The seven pillars in this build" actions={<span className="text-xs text-ink-500">PRD §4</span>}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {PILLARS.map((p) => {
            const body = (
              <div className="group h-full rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 transition hover:border-cyan-400/30 hover:bg-white/[0.04]">
                <div className="flex items-start justify-between gap-2">
                  <span className="font-display text-2xl font-bold text-white/15 transition group-hover:text-cyan-300/50">{p.n}</span>
                  <Badge tone={p.tone}>{p.state}</Badge>
                </div>
                <div className="mt-2 font-display text-[15px] font-semibold text-ink-100">{p.name}</div>
                <div className="mt-1 text-xs leading-relaxed text-ink-500">{p.what}</div>
              </div>);
            return p.to ? <Link key={p.n} to={p.to}>{body}</Link> : <div key={p.n}>{body}</div>;
          })}
          <div className="rounded-xl border border-dashed border-amber-400/25 bg-amber-400/[0.03] p-4">
            <div className="flex items-center justify-between"><span className="font-display text-sm font-semibold text-amber-200">Not in this build</span><Badge tone="warn">Open</Badge></div>
            <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-ink-300">
              <li><span className="text-ink-100">Trust Ladder</span>: graduated containment. {h.policy_engine.reason.split("(")[0].trim()}; the gateway fails closed.</li>
              <li><span className="text-ink-100">Behavior Engine</span>: signal fixed at 0.</li>
            </ul>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1 text-[11px] text-ink-500">
          <span><Badge tone="ok">Live</Badge> runs in the API</span><span><Badge tone="info">Analysis</Badge> real engine, what-if only</span>
          <span><Badge tone="info">Measured</Badge> benchmarked</span><span><Badge tone="violet">Engine</Badge> unit-tested, no UI</span>
          <span><Badge tone="warn">Partial</Badge> part of the pillar</span>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Card title="Recent activity" actions={<Link to="/audit" className="text-xs font-medium text-cyan-300 hover:underline">Full audit log →</Link>}>
          {recent.loading ? <Loading rows={5} /> : recent.error ? <ErrorBox message={recent.error} /> : (recent.data ?? []).length === 0 ? <Empty>No events yet.</Empty> : (
            <ol className="relative space-y-4 before:absolute before:top-1 before:bottom-1 before:left-[5px] before:w-px before:bg-white/[0.08]">
              {recent.data!.map((e) => (
                <li key={e.seq} className="relative flex items-start gap-4 pl-6 text-sm">
                  <span className={`absolute top-1.5 left-0 h-[11px] w-[11px] rounded-full ring-4 ring-ink-950 ${DOT[e.kind] ?? "bg-ink-500"}`} />
                  <div className="min-w-0 flex-1"><div className="text-ink-100">{describe(e)}</div>
                    <div className="mt-0.5 text-xs text-ink-500">{e.ts.replace("T", " ").slice(0, 19)} UTC · {e.actor ?? "system"}</div></div>
                  <span className="font-mono text-[11px] text-ink-500">#{e.seq}</span>
                </li>))}
            </ol>)}
        </Card>
        <Card title="Platform">
          <ul className="divide-y divide-white/[0.05] text-sm">
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Database</span><Badge tone="ok">{h.database}</Badge></li>
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Event bus</span><Badge tone="muted">{h.event_bus}</Badge></li>
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Embeddings ({h.embeddings.model})</span>
              <Badge tone={h.embeddings.mode === "minilm-onnx" ? "ok" : h.embeddings.mode === "lexical-fallback" ? "warn" : "muted"}>
                {h.embeddings.mode === "uninitialised" ? "loads on first use" : h.embeddings.mode}</Badge></li>
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Gateway enforcement</span><Badge tone="warn">fail-closed</Badge></li>
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Behavior Engine</span><Badge tone="warn">not implemented</Badge></li>
            <li className="flex items-center justify-between py-2.5"><span className="text-ink-300">Trust Ladder policy engine</span><Badge tone="warn">not implemented</Badge></li>
          </ul>
        </Card>
      </div>
    </div>
  );
}
