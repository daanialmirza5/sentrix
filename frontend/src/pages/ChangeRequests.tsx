import { useState } from "react";
import { post, type Agent, type ChangeRequest } from "../services/api";
import { useAuth } from "../App";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Spinner, fmtTime, toast, useApi } from "../components/ui";

const TONE: Record<string, "warn" | "ok" | "bad"> = { pending: "warn", approved: "ok", rejected: "bad" };

export default function ChangeRequests() {
  const { user } = useAuth();
  const crs = useApi<ChangeRequest[]>("/v1/change-requests");
  const agents = useApi<Agent[]>("/v1/agents");
  const [agent, setAgent] = useState("proc-agent-07");
  const [tools, setTools] = useState("erp.create_po");
  const [why, setWhy] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<{ id: string; action: "approve" | "reject" } | null>(null);
  const isOwner = !!user?.roles.includes("owner");
  const isSecurity = !!user?.roles.includes("security");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const cr = await post<ChangeRequest>("/v1/change-requests", { agent_id: agent, justification: why,
        changes: { add_tools: tools.split(",").map((t) => t.trim()).filter(Boolean) } });
      toast.ok(`Submitted ${cr.id}, signed by ${cr.requester}. It now needs a security approver.`);
      setWhy(""); void crs.reload();
    } catch (err) { toast.err(err instanceof Error ? err.message : String(err)); }
    finally { setBusy(false); }
  }
  async function decide() {
    if (!confirm) return;
    try {
      const r = await post<ChangeRequest & { new_version?: number }>(`/v1/change-requests/${confirm.id}/${confirm.action}`, { note: `${confirm.action}d via console` });
      toast.ok(confirm.action === "approve" ? `Approved. Contract is now v${r.new_version}.` : `Rejected ${confirm.id}.`);
      void crs.reload();
    } catch (err) { toast.err(err instanceof Error ? err.message : String(err)); }
    setConfirm(null);
  }

  return (
    <>
      <PageHeader title="Change Requests" subtitle="Signed Role Change Request workflow. The owner submits, and a different security approver signs." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="New request" className="lg:col-span-1">
          {!isOwner ? <p className="text-sm text-ink-500">Only agent owners can submit. Sign in as Meera or Arjun.</p> : (
            <form onSubmit={submit} className="space-y-3">
              <label className="block text-xs text-ink-500">Agent<select className="mt-1 w-full" value={agent} onChange={(e) => setAgent(e.target.value)}>
                {(agents.data ?? []).filter((a) => a.contract_version).map((a) => <option key={a.id}>{a.id}</option>)}</select></label>
              <label className="block text-xs text-ink-500">Add tools (comma separated)<input className="mt-1 w-full font-mono" value={tools} onChange={(e) => setTools(e.target.value)} /></label>
              <label className="block text-xs text-ink-500">Business justification<textarea className="mt-1 h-24 w-full" value={why} onChange={(e) => setWhy(e.target.value)} minLength={10} required /></label>
              <Button type="submit" disabled={busy || why.length < 10}>{busy && <Spinner />}Sign and submit</Button>
            </form>)}
        </Card>
        <Card title="Requests" className="lg:col-span-2">
          {crs.loading ? <Loading /> : crs.error ? <ErrorBox message={crs.error} /> : (crs.data ?? []).length === 0 ? <Empty>No change requests.</Empty> : (
            <ul className="space-y-3">{crs.data!.map((c) => (
              <li key={c.id} className="rounded-md border border-ink-700 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-mono text-sm">{c.id} · {c.agent_id} · base v{c.base_version}</div>
                  <Badge tone={TONE[c.status]}>{c.status}{c.resulting_version ? ` → v${c.resulting_version}` : ""}</Badge>
                </div>
                <div className="mt-2 text-sm text-ink-300">{c.justification}</div>
                <div className="mt-2 font-mono text-xs text-teal-300">{JSON.stringify(c.changes)}</div>
                <div className="mt-2 text-xs text-ink-500">Requested by {c.requester} {c.requester_signed && "(signed)"} · {fmtTime(c.created_at)}
                  {c.approver && ` · decided by ${c.approver}${c.approver_signed ? " (signed)" : ""}`}</div>
                {c.status === "pending" && isSecurity && (
                  <div className="mt-3 flex gap-2">
                    <Button onClick={() => setConfirm({ id: c.id, action: "approve" })}>Approve</Button>
                    <Button variant="ghost" onClick={() => setConfirm({ id: c.id, action: "reject" })}>Reject</Button>
                  </div>)}
              </li>))}</ul>)}
        </Card>
      </div>
      {confirm && (
        <div className="fixed inset-0 z-40 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Confirm decision">
          <div className="w-full max-w-md rounded-lg border border-ink-700 bg-ink-900 p-5">
            <h3 className="font-semibold">{confirm.action === "approve" ? "Approve and sign" : "Reject"} {confirm.id}?</h3>
            <p className="mt-2 text-sm text-ink-300">{confirm.action === "approve" ? "This signs a new contract version with your security key and supersedes the current one." : "The request will be closed without changing the contract."}</p>
            <div className="mt-4 flex justify-end gap-2"><Button variant="ghost" onClick={() => setConfirm(null)}>Cancel</Button>
              <Button variant={confirm.action === "approve" ? "primary" : "danger"} onClick={decide}>Confirm</Button></div>
          </div>
        </div>)}
    </>
  );
}
