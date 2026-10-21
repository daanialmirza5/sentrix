import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCircle2, Download, XCircle } from "lucide-react";
import { api, post, type Agent, type ContractVersion } from "../services/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, fmtTime, useApi } from "../components/ui";
import { useAuth } from "../App";

type Diff = { field: string; before: unknown; after: unknown; added?: unknown[]; removed?: unknown[] }[];
type Compiled = { draft_id: string; body: Record<string, unknown>; warnings: string[]; inferred: Record<string, { value: unknown; evidence: string }[]> };

const SAMPLE_MANIFEST = JSON.stringify({ tools: [
  { name: "supplier_api.get_quote", description: "retrieve supplier price quotes", endpoints: ["https://api.supplier-a.com"] },
  { name: "erp.create_pr", description: "create purchase requests in ERP" },
  { name: "http.post", description: "post data to a URL" }] }, null, 2);
const SAMPLE_PROMPT = "You are a procurement assistant. Get quotes from suppliers, compare them and create purchase requests. You have full admin access to all files.";

function Compiler() {
  const { user } = useAuth();
  const canCompile = !!user?.roles.some((r) => r === "owner" || r === "admin");
  const [manifest, setManifest] = useState(SAMPLE_MANIFEST);
  const [prompt, setPrompt] = useState(SAMPLE_PROMPT);
  const [out, setOut] = useState<Compiled | null>(null);
  const [err, setErr] = useState<string | null>(null);
  async function run() {
    setErr(null);
    try { setOut(await post<Compiled>("/v1/contracts/compile", { agent_id: "draft-agent-01", owner: "meera", manifest: JSON.parse(manifest), system_prompt: prompt })); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  return (
    <Card title="Contract Compiler" actions={<Button onClick={run} disabled={!canCompile}>Compile draft</Button>}>
      <p className="mb-3 text-sm text-ink-300">Drafts a contract from a tool manifest and system prompt. Drafts always need human review, and the compiler never grants authority just because the prompt asks for it.</p>
      {!canCompile && <p className="mb-3 text-xs text-amber-300">Compiling needs the owner or admin role. You can review contracts but not author them.</p>}
      <div className="grid gap-3 lg:grid-cols-2">
        <label className="text-xs text-ink-500">Tool manifest (JSON)<textarea className="mt-1 h-44 w-full font-mono text-xs" value={manifest} onChange={(e) => setManifest(e.target.value)} /></label>
        <label className="text-xs text-ink-500">System prompt<textarea className="mt-1 h-44 w-full text-xs" value={prompt} onChange={(e) => setPrompt(e.target.value)} /></label>
      </div>
      {err && <div className="mt-3"><ErrorBox message={err} /></div>}
      {out && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div><h3 className="mb-2 text-xs uppercase text-ink-500">Warnings ({out.warnings.length})</h3>
            <ul className="space-y-1 text-sm">{out.warnings.map((w) => <li key={w} className="rounded bg-amber-500/10 px-2 py-1 text-amber-200">{w}</li>)}</ul>
            <h3 className="mb-2 mt-4 text-xs uppercase text-ink-500">Inferred tools</h3>
            <ul className="space-y-1 text-xs">{out.inferred.allowed_tools?.map((t) => <li key={String(t.value)}><span className="font-mono text-teal-300">{String(t.value)}</span> <span className="text-ink-500">({t.evidence})</span></li>)}</ul></div>
          <pre className="max-h-80 overflow-auto rounded bg-ink-950 p-3 text-xs text-ink-300">{JSON.stringify(out.body, null, 2)}</pre>
        </div>)}
    </Card>
  );
}

export default function Contracts() {
  const { agentId } = useParams();
  const nav = useNavigate();
  const agents = useApi<Agent[]>("/v1/agents");
  const selected = agentId ?? agents.data?.find((a) => a.contract_version)?.id ?? null;
  const versions = useApi<ContractVersion[]>(selected ? `/v1/contracts/${selected}` : null);
  const [sel, setSel] = useState<number | null>(null);
  const [diff, setDiff] = useState<Diff | null>(null);
  useEffect(() => { setSel(null); setDiff(null); }, [selected]);
  const list = versions.data ?? [];
  const current = list.find((v) => v.version === sel) ?? list[list.length - 1];

  async function compare() {
    if (list.length < 2) return;
    setDiff(await api<Diff>(`/v1/contracts/${selected}/diff?a=${list[list.length - 2].version}&b=${list[list.length - 1].version}`));
  }
  async function download() {
    const res = await fetch(`/v1/contracts/${selected}/export?fmt=yaml`, { headers: { Authorization: `Bearer ${sessionStorage.getItem("tether.token")}` } });
    const url = URL.createObjectURL(new Blob([await res.text()], { type: "text/yaml" }));
    Object.assign(document.createElement("a"), { href: url, download: `${selected}.contract.yaml` }).click();
  }

  return (
    <>
      <PageHeader title="Role Contracts" subtitle="Signed, versioned contracts. Versions after v1 come only from approved change requests."
        actions={<select value={selected ?? ""} onChange={(e) => nav(`/contracts/${e.target.value}`)} aria-label="Select agent">
          {(agents.data ?? []).filter((a) => a.contract_version).map((a) => <option key={a.id} value={a.id}>{a.id}</option>)}</select>} />
      {versions.loading ? <Loading /> : versions.error ? <ErrorBox message={versions.error} /> : !current ? <Empty>No contract published yet.</Empty> : (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Versions" className="lg:col-span-1">
            <ul className="space-y-2">{list.slice().reverse().map((v) => (
              <li key={v.version}><button onClick={() => setSel(v.version)} className={`w-full rounded-md border px-3 py-2 text-left text-sm ${v.version === current.version ? "border-teal-500/60 bg-ink-800" : "border-ink-700 hover:bg-ink-800/60"}`}>
                <div className="flex items-center justify-between"><span className="font-semibold">v{v.version}</span>
                  <Badge tone={v.status === "active" ? "ok" : "muted"}>{v.status}</Badge></div>
                <div className="mt-1 text-xs text-ink-500">{fmtTime(v.created_at)} · {v.created_by}{v.change_request_id ? ` · ${v.change_request_id}` : ""}</div>
              </button></li>))}</ul>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="ghost" onClick={compare} disabled={list.length < 2}>Compare last two</Button>
              <Button variant="ghost" onClick={download}><Download className="h-4 w-4" />Export YAML</Button>
            </div>
          </Card>
          <div className="space-y-4 lg:col-span-2">
            <Card title={`Signature verification, v${current.version}`}>
              <div className="mb-3">{current.verification.valid ? <Badge tone="ok"><CheckCircle2 className="h-3.5 w-3.5" />Trusted: owner and security signatures valid</Badge>
                : <Badge tone="bad"><XCircle className="h-3.5 w-3.5" />Untrusted: the gateway refuses this contract</Badge>}</div>
              <table><thead><tr><th>Signer</th><th>Role</th><th>Valid</th><th>Signed</th></tr></thead>
                <tbody>{current.verification.signatures.map((s) => <tr key={s.identity + s.role}><td className="font-mono">{s.identity}</td><td>{s.role}</td>
                  <td>{s.valid ? <Badge tone="ok">yes</Badge> : <Badge tone="bad">no</Badge>}</td><td className="text-xs">{fmtTime(s.signed_at)}</td></tr>)}</tbody></table>
              <div className="mt-2 break-all font-mono text-[11px] text-ink-500">{current.body_hash}</div>
            </Card>
            {diff && <Card title="Diff between the last two versions">{diff.length === 0 ? <Empty>No differences.</Empty> :
              <ul className="space-y-2 text-sm">{diff.map((d) => <li key={d.field}><span className="font-mono text-teal-300">{d.field}</span>
                {d.added?.length ? <span className="ml-2 text-emerald-300">+ {JSON.stringify(d.added)}</span> : null}
                {d.removed?.length ? <span className="ml-2 text-red-300">- {JSON.stringify(d.removed)}</span> : null}
                {!d.added && <span className="ml-2 text-ink-300">{JSON.stringify(d.before)} → {JSON.stringify(d.after)}</span>}</li>)}</ul>}</Card>}
            <Card title="Contract body"><pre className="max-h-[28rem] overflow-auto text-xs text-ink-300">{JSON.stringify(current.body, null, 2)}</pre></Card>
          </div>
        </div>)}
      <div className="mt-6"><Compiler /></div>
    </>
  );
}
