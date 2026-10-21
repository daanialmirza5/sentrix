import { useState } from "react";
import { FlaskConical, ShieldAlert } from "lucide-react";
import { post, type Agent, type Analysis, type Signals } from "../services/api";
import { Badge, Button, Card, ErrorBox, PageHeader, Spinner, useApi } from "../components/ui";

type Preset = { label: string; tool: string; args: Record<string, unknown>; steps?: number; fixture?: string };
const PRESETS: Preset[] = [
  { label: "In-role: get a supplier quote", tool: "supplier_api.get_quote", args: { supplier: "supplier-a", item: "A4 paper" } },
  { label: "In-role: raise a purchase request", tool: "erp.create_pr", args: { item: "A4 paper", amount_inr: 98000 } },
  { label: "Over limit: PR above INR 5,00,000", tool: "erp.create_pr", args: { item: "servers", amount_inr: 900000 } },
  { label: "Out-of-role read 1 step after poisoned quote", tool: "fs.read", args: { path: "/hr/salary_backup.xlsx" }, steps: 1, fixture: "poisoned_quote" },
  { label: "Unapproved capability (erp.create_po)", tool: "erp.create_po", args: { item: "toner", amount_inr: 40000 } },
  { label: "Outbound to mock destination", tool: "http.post", args: { url: "https://mock-sink.invalid/upload", body: "quarterly summary" } },
];

const NAMES: Record<keyof Signals, string> = { R: "Role-fit", B: "Behavior", P: "Provenance", S: "Sensitivity × egress" };
const tone = (risk: number) => (risk >= 75 ? "bad" : risk >= 30 ? "warn" : "ok");

export default function SignalLab() {
  const agents = useApi<Agent[]>("/v1/agents");
  const [agent, setAgent] = useState("proc-agent-07");
  const [tool, setTool] = useState(PRESETS[0].tool);
  const [args, setArgs] = useState(JSON.stringify(PRESETS[0].args, null, 2));
  const [steps, setSteps] = useState<string>("");
  const [fixture, setFixture] = useState("");
  const [res, setRes] = useState<Analysis | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function load(p: Preset) {
    setTool(p.tool); setArgs(JSON.stringify(p.args, null, 2)); setSteps(p.steps?.toString() ?? ""); setFixture(p.fixture ?? "");
  }
  async function run() {
    setBusy(true); setErr(null);
    try {
      const parsed = JSON.parse(args);
      setRes(await post<Analysis>("/v1/analyze", { agent_id: agent, tool, args: parsed,
        steps_since_untrusted: steps === "" ? null : Number(steps), fixture: fixture || null }));
    } catch (e) { setErr(e instanceof SyntaxError ? `Args are not valid JSON: ${e.message}` : e instanceof Error ? e.message : String(e)); setRes(null); }
    finally { setBusy(false); }
  }

  return (
    <>
      <PageHeader title="Signal Lab" subtitle="What-if analysis: score a proposed action with the real detection engines. Nothing executes and no state changes." />
      <div className="grid gap-4 xl:grid-cols-5">
        <Card title="Proposed action" className="xl:col-span-2">
          <div className="mb-4 flex flex-wrap gap-2">{PRESETS.map((p) => (
            <button key={p.label} onClick={() => load(p)} className="rounded-full border border-ink-700 px-3 py-1 text-xs text-ink-300 hover:border-teal-500/60 hover:text-ink-100">{p.label}</button>))}</div>
          <div className="space-y-3">
            <label className="block text-xs text-ink-500">Agent (contract to score against)
              <select className="mt-1 w-full" value={agent} onChange={(e) => setAgent(e.target.value)}>
                {(agents.data ?? []).filter((a) => a.contract_version).map((a) => <option key={a.id}>{a.id}</option>)}</select></label>
            <label className="block text-xs text-ink-500">Tool<input className="mt-1 w-full font-mono" value={tool} onChange={(e) => setTool(e.target.value)} /></label>
            <label className="block text-xs text-ink-500">Arguments (JSON)<textarea className="mt-1 h-28 w-full font-mono text-xs" value={args} onChange={(e) => setArgs(e.target.value)} /></label>
            <div className="grid grid-cols-[1fr_9rem] gap-3">
              <label className="block text-xs text-ink-500">Untrusted content ingested
                <select className="mt-1 w-full" value={fixture} onChange={(e) => setFixture(e.target.value)}>
                  <option value="">None</option><option value="poisoned_quote">supplier_quote.pdf (test marker)</option><option value="clean_quote">quote_clean.pdf (clean)</option></select></label>
              <label className="block text-xs text-ink-500">Steps since ingestion
                <input className="mt-1 w-full" type="number" min={0} max={100} value={steps} onChange={(e) => setSteps(e.target.value)} disabled={!fixture} /></label>
            </div>
            <Button onClick={run} disabled={busy}>{busy ? <Spinner /> : <FlaskConical className="h-4 w-4" />}Analyse</Button>
            {err && <ErrorBox message={err} />}
          </div>
        </Card>

        <div className="space-y-4 xl:col-span-3">
          {!res ? <Card><div className="py-10 text-center text-sm text-ink-500">Pick a preset or describe an action, then press Analyse.</div></Card> : (<>
            <Card>
              <div className="flex flex-wrap items-center gap-6">
                <div>
                  <div className="text-xs uppercase tracking-wide text-ink-500">Fused risk</div>
                  <div className="mt-1 flex items-baseline gap-2"><span className="text-4xl font-semibold tabular-nums">{res.risk.toFixed(1)}</span><span className="text-ink-500">/ 100</span></div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone={tone(res.risk)}>{res.risk >= 75 ? "high" : res.risk >= 30 ? "elevated" : "low"}</Badge>
                  {res.override && <Badge tone="bad"><ShieldAlert className="h-3.5 w-3.5" />{res.override} override</Badge>}
                  {res.would_hard_deny ? <Badge tone="bad">contract rule would deny</Badge> : <Badge tone="ok">no hard deny</Badge>}
                  <Badge>trust level: n/a (policy engine not implemented)</Badge>
                </div>
              </div>
              <p className="mt-4 text-sm text-ink-100">{res.explanation.why}</p>
              {res.explanation.cause && <p className="mt-2 text-sm text-amber-200">Cause: {res.explanation.cause}</p>}
              <p className="mt-2 font-mono text-xs text-ink-500">{res.explanation.factors}</p>
            </Card>
            <Card title="Signals and contributions (noisy-OR)">
              <table>
                <thead><tr><th>Signal</th><th className="text-right">Value s</th><th>Contribution</th></tr></thead>
                <tbody>{(Object.keys(NAMES) as (keyof Signals)[]).map((k) => {
                  const off = res.disabled_signals.includes(k);
                  return (
                    <tr key={k}><td>{NAMES[k]}{off && <span className="ml-2 text-xs text-ink-500">(disabled, not implemented)</span>}</td>
                      <td className="text-right font-mono tabular-nums">{off ? "—" : res.signals[k].toFixed(3)}</td>
                      <td className="w-1/2"><div className="flex items-center gap-2">
                        <div className="h-2 flex-1 rounded-full bg-ink-800"><div className="h-2 rounded-full bg-teal-400" style={{ width: `${res.contributions[k]}%` }} /></div>
                        <span className="w-12 text-right font-mono text-xs tabular-nums text-ink-300">{res.contributions[k].toFixed(1)}%</span></div></td></tr>);
                })}</tbody>
              </table>
            </Card>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Role-fit evidence">
                <div className="text-xs text-ink-500">Action text: <span className="font-mono text-ink-300">{res.action.text}</span></div>
                {res.role_fit.rules.length ? <ul className="mt-3 space-y-1.5 text-sm">{res.role_fit.rules.map((r) => (
                  <li key={r.rule} className="flex gap-2"><Badge tone={res.role_fit.hard_deny.includes(r.rule) ? "bad" : "warn"}>{r.rule}</Badge><span className="text-ink-300">{r.detail}</span></li>))}</ul>
                  : <p className="mt-3 text-sm text-ink-300">No contract rule triggered.</p>}
                {res.role_fit.fit !== null && <p className="mt-3 text-xs text-ink-500">Nearest anchor “{res.role_fit.nearest_anchor}” · cosine {res.role_fit.fit.toFixed(3)} · engine <span className="font-mono">{res.role_fit.mode}</span></p>}
              </Card>
              <Card title="Deception and provenance">
                <ul className="space-y-1.5 text-sm text-ink-300">
                  <li>Honey-resource: {res.deception.honey ? <span className="font-mono text-red-300">{res.deception.honey}</span> : "none"}</li>
                  <li>Canaries in payload: {res.deception.canaries.length ? res.deception.canaries.map((c) => `${c.masked} (agent ${c.owner})`).join(", ") : "none"}</li>
                  <li>DLP matches: {res.deception.dlp.length ? res.deception.dlp.join(", ") : "none"}</li>
                  <li>Taint: {res.provenance.tau !== null ? `τ = ${res.provenance.tau} after ${res.provenance.steps_since} step(s) from ${res.provenance.source}` : "no untrusted content in context"}</li>
                  {res.provenance.attribution?.span && <li>Attributed span: page {res.provenance.attribution.span.page}, line {res.provenance.attribution.span.line}
                    {res.provenance.attribution.uncertain ? " (uncertain)" : ` (confidence ${res.provenance.attribution.confidence})`}</li>}
                </ul>
              </Card>
            </div>
            <p className="text-xs text-ink-500">{res.note}</p>
          </>)}
        </div>
      </div>
    </>
  );
}
