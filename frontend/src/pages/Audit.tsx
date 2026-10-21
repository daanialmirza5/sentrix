import { Fragment, useState } from "react";
import { ChevronRight, ShieldCheck, ShieldX } from "lucide-react";
import { api, type AuditEvent, type ChainCheck } from "../services/api";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, Spinner, useApi } from "../components/ui";

const KIND_TONE: Record<string, "info" | "ok" | "warn" | "bad" | "muted"> = { contract: "ok", change_request: "info", token: "muted", gateway: "bad", admin: "warn" };

export default function Audit() {
  const [kind, setKind] = useState("all");
  const events = useApi<AuditEvent[]>("/v1/audit/events?limit=200");
  const [check, setCheck] = useState<ChainCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<number | null>(null);
  async function verify() {
    setBusy(true);
    try { setCheck(await api<ChainCheck>("/v1/audit/verify")); } finally { setBusy(false); }
  }
  const rows = (events.data ?? []).filter((e) => kind === "all" || e.kind === kind);
  const kinds = Array.from(new Set((events.data ?? []).map((e) => e.kind)));

  return (
    <>
      <PageHeader title="Audit Log" subtitle="Append-only, hash-chained events. Each hash covers the event plus the previous hash."
        actions={<div className="flex gap-2"><Button variant="ghost" onClick={() => void events.reload()}>Refresh</Button>
          <Button onClick={verify} disabled={busy}>{busy && <Spinner />}Verify chain</Button></div>} />
      {check && (
        <div className={`mb-4 flex items-center gap-2 rounded-md p-3 text-sm ${check.valid ? "bg-emerald-500/10 text-emerald-200" : "bg-red-500/10 text-red-200"}`} role="status">
          {check.valid ? <ShieldCheck className="h-4 w-4" /> : <ShieldX className="h-4 w-4" />}
          {check.valid ? `Chain intact: ${check.checked} events recomputed, head ${check.head?.slice(0, 23)}…`
            : `Chain broken at seq ${check.broken_at_seq}: ${check.reason}`}
        </div>)}
      <Card actions={<select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter by kind">
        <option value="all">All kinds</option>{kinds.map((k) => <option key={k}>{k}</option>)}</select>} title={`${rows.length} events`}>
        {events.loading ? <Loading /> : events.error ? <ErrorBox message={events.error} /> : rows.length === 0 ? <Empty>No events.</Empty> : (
          <div className="overflow-x-auto"><table>
            <thead><tr><th>Seq</th><th>Time (UTC)</th><th>Kind</th><th>Agent</th><th>Verdict</th><th>Actor</th><th>Hash</th></tr></thead>
            <tbody>{rows.map((e) => (
              <Fragment key={e.seq}>
                <tr className="cursor-pointer" onClick={() => setOpen(open === e.seq ? null : e.seq)} aria-expanded={open === e.seq}>
                  <td className="font-mono"><span className="inline-flex items-center gap-1"><ChevronRight className={`h-3.5 w-3.5 text-ink-500 transition-transform ${open === e.seq ? "rotate-90" : ""}`} />{e.seq}</span></td>
                  <td className="whitespace-nowrap font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</td>
                  <td><Badge tone={KIND_TONE[e.kind] ?? "muted"}>{e.kind}</Badge></td><td className="font-mono text-xs">{e.agent_id ?? "—"}</td>
                  <td>{e.verdict}</td><td>{e.actor}</td><td className="font-mono text-[11px] text-ink-500" title={e.hash}>{e.hash.slice(7, 19)}…</td></tr>
                {open === e.seq && (
                  <tr className="hover:bg-transparent"><td colSpan={7} className="bg-ink-950/60">
                    <div className="grid gap-3 py-2 lg:grid-cols-2">
                      <div><div className="mb-1 text-xs uppercase text-ink-500">Details</div>
                        <pre className="max-h-64 overflow-auto rounded bg-ink-950 p-3 text-xs text-ink-300">{JSON.stringify(e.details, null, 2)}</pre></div>
                      <div className="space-y-2 text-xs"><div className="uppercase text-ink-500">Chain link</div>
                        <div><span className="text-ink-500">prev_hash</span><div className="break-all font-mono text-ink-300">{e.prev_hash}</div></div>
                        <div><span className="text-ink-500">hash = sha256(event ‖ prev_hash)</span><div className="break-all font-mono text-teal-300">{e.hash}</div></div>
                        {e.tool && <div><span className="text-ink-500">tool</span> <span className="font-mono">{e.tool}</span></div>}</div>
                    </div></td></tr>)}
              </Fragment>))}</tbody>
          </table></div>)}
      </Card>
    </>
  );
}
