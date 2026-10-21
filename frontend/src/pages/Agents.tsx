import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Copy, Plus, Search } from "lucide-react";
import { post, type Agent } from "../services/api";
import { useAuth } from "../App";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Spinner, fmtTime, toast, useApi } from "../components/ui";

function RegisterDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ agent_id: "", name: "", owner: "meera", role: "procurement" });
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const valid = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,79}$/.test(f.agent_id) && f.name.trim() && f.role.trim();
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try { setSecret((await post<{ agent_secret: string }>("/v1/agents", f)).agent_secret); onDone(); toast.ok(`Registered ${f.agent_id}.`); }
    catch (err) { toast.err(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  return (
    <div className="fixed inset-0 z-40 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Register agent">
      <div className="w-full max-w-md rounded-lg border border-ink-700 bg-ink-900 p-5">
        <h3 className="font-semibold">Register agent</h3>
        {secret ? (
          <div className="mt-3 space-y-3 text-sm">
            <p className="text-ink-300">Agent secret. It is shown <strong>once</strong>; only its hash is stored. The agent uses it to request task tokens.</p>
            <code className="block break-all rounded bg-ink-950 p-3 font-mono text-xs text-teal-300">{secret}</code>
            <p className="text-xs text-ink-500">Next step: a security approver publishes v1 of its Role Contract.</p>
            <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => { void navigator.clipboard?.writeText(secret); toast.ok("Copied."); }}><Copy className="h-4 w-4" />Copy</Button>
              <Button onClick={onClose}>Done</Button></div>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-3 space-y-3">
            <label className="block text-xs text-ink-500">Agent ID<input className="mt-1 w-full font-mono" value={f.agent_id} placeholder="proc-agent-11" onChange={(e) => setF({ ...f, agent_id: e.target.value })} /></label>
            <label className="block text-xs text-ink-500">Display name<input className="mt-1 w-full" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs text-ink-500">Owner<select className="mt-1 w-full" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })}><option>meera</option><option>arjun</option></select></label>
              <label className="block text-xs text-ink-500">Role<input className="mt-1 w-full" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} /></label>
            </div>
            <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={!valid || busy}>{busy && <Spinner />}Register</Button></div>
          </form>)}
      </div>
    </div>
  );
}

export default function Agents() {
  const { user } = useAuth();
  const canRegister = !!user?.roles.some((r) => r === "admin" || r === "owner");
  const [registering, setRegistering] = useState(false);
  const { data, error, loading, reload } = useApi<Agent[]>("/v1/agents");
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [role, setRole] = useState("all");
  const roles = useMemo(() => Array.from(new Set((data ?? []).map((a) => a.role))).sort(), [data]);
  const rows = (data ?? []).filter((a) => (role === "all" || a.role === role) &&
    `${a.id} ${a.name} ${a.owner}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <PageHeader title="Agents" subtitle="Registered agents and their signed contract versions. Live risk scores and trust levels need the policy engine, which is not implemented; use Signal Lab for what-if scoring."
        actions={canRegister && <Button onClick={() => setRegistering(true)}><Plus className="h-4 w-4" />Register agent</Button>} />
      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <label className="relative flex-1"><Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-500" />
            <input className="w-full pl-9" placeholder="Search by id, name or owner" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search agents" /></label>
          <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Filter by role">
            <option value="all">All roles</option>{roles.map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>
        {loading ? <Loading /> : error ? <ErrorBox message={error} /> : rows.length === 0 ? <Empty>No agents match.</Empty> : (
          <div className="overflow-x-auto"><table>
            <thead><tr><th>Agent</th><th>Owner</th><th>Role</th><th>Kind</th><th>Contract</th><th>Canary</th><th>Registered</th></tr></thead>
            <tbody>{rows.map((a) => (
              <tr key={a.id} className={a.contract_version ? "cursor-pointer" : ""} onClick={() => a.contract_version && nav(`/contracts/${a.id}`)}>
                <td><div>{a.name}</div><div className="font-mono text-xs text-ink-500">{a.id}</div></td>
                <td>{a.owner}</td><td>{a.role}</td><td><Badge>{a.kind}</Badge></td>
                <td>{a.contract_version ? <Link className="text-teal-300 hover:underline" to={`/contracts/${a.id}`}>v{a.contract_version}</Link> : <Badge tone="warn">none</Badge>}</td>
                <td className="font-mono text-xs text-ink-300" title="Masked; full value is never shown to agents">{a.canary}</td>
                <td className="text-xs text-ink-300">{fmtTime(a.created_at)}</td>
              </tr>))}</tbody>
          </table></div>)}
      </Card>
      {registering && <RegisterDialog onClose={() => setRegistering(false)} onDone={() => void reload()} />}
    </>
  );
}
