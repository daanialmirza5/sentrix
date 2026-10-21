import { useMemo, useState } from "react";
import { KeyRound } from "lucide-react";
import { post, type TokenRow } from "../services/api";
import { useAuth } from "../App";
import { Badge, Button, Card, Empty, ErrorBox, Loading, PageHeader, toast, useApi } from "../components/ui";

const TONE = { active: "ok", expired: "muted", revoked: "bad" } as const;
const t = (s: number) => new Date(s * 1000).toLocaleString();

export default function Credentials() {
  const { user } = useAuth();
  const canRevoke = !!user?.roles.includes("security");
  const { data, error, loading, reload } = useApi<TokenRow[]>("/v1/tokens");
  const [status, setStatus] = useState("all");
  const [target, setTarget] = useState<TokenRow | null>(null);
  const [reason, setReason] = useState("");
  const rows = useMemo(() => (data ?? []).filter((r) => status === "all" || r.status === status), [data, status]);
  const counts = useMemo(() => ({ active: 0, expired: 0, revoked: 0, ...Object.fromEntries(
    ["active", "expired", "revoked"].map((s) => [s, (data ?? []).filter((r) => r.status === s).length])) }), [data]);

  async function revoke() {
    if (!target) return;
    try {
      const r = await post<{ revoked: string[]; cascade: number }>(`/v1/tokens/${target.jti}/revoke`, { reason });
      toast.ok(`Revoked ${target.jti}${r.cascade ? ` and ${r.cascade} delegated token(s)` : ""}.`);
      setTarget(null); setReason(""); void reload();
    } catch (e) { toast.err(e instanceof Error ? e.message : String(e)); }
  }

  return (
    <>
      <PageHeader title="Credentials" subtitle="Task-bound tokens from the broker. Scope = contract ∩ task (∩ parent); TTL 5–15 min; bound to a contract version." />
      <div className="mb-4 grid grid-cols-3 gap-4">
        {(["active", "expired", "revoked"] as const).map((s) => (
          <Card key={s}><div className="text-xs uppercase tracking-wide text-ink-500">{s}</div><div className="mt-2 text-2xl font-semibold tabular-nums">{counts[s]}</div></Card>))}
      </div>
      <Card title={`${rows.length} tokens`} actions={<select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
        <option value="all">All statuses</option><option value="active">Active</option><option value="expired">Expired</option><option value="revoked">Revoked</option></select>}>
        {loading ? <Loading /> : error ? <ErrorBox message={error} /> : rows.length === 0 ? <Empty>No tokens yet. Tokens are minted by POST /v1/tasks with agent credentials.</Empty> : (
          <div className="overflow-x-auto"><table>
            <thead><tr><th>Token</th><th>Agent</th><th>Scope</th><th>Contract</th><th>Expires</th><th>Status</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.jti}>
                <td><div className="font-mono text-xs">{r.jti}</div>{r.parent_jti && <div className="text-[11px] text-ink-500">delegated from {r.parent_jti} (depth {r.depth})</div>}</td>
                <td className="font-mono text-xs">{r.agent_id}<div className="text-ink-500">{r.task_id}</div></td>
                <td><div className="flex max-w-xs flex-wrap gap-1">{r.scope.map((s) => <span key={s} className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[11px] text-ink-300">{s}</span>)}</div></td>
                <td>v{r.contract_version}</td>
                <td className="whitespace-nowrap text-xs text-ink-300">{t(r.expires_at)}</td>
                <td><Badge tone={TONE[r.status]}>{r.status}</Badge>{r.revoked_reason && <div className="mt-1 max-w-[14rem] text-[11px] text-ink-500">{r.revoked_reason}</div>}</td>
                <td>{canRevoke && r.status === "active" && <Button variant="ghost" onClick={() => setTarget(r)}><KeyRound className="h-3.5 w-3.5" />Revoke</Button>}</td>
              </tr>))}</tbody>
          </table></div>)}
        {!canRevoke && <p className="mt-3 text-xs text-ink-500">Revocation requires the security role.</p>}
      </Card>
      {target && (
        <div className="fixed inset-0 z-40 flex animate-fade-in items-center justify-center bg-black/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Confirm revocation">
          <div className="w-full max-w-md rounded-lg border border-ink-700 bg-ink-900 p-5">
            <h3 className="font-semibold">Revoke {target.jti}?</h3>
            <p className="mt-2 text-sm text-ink-300">The token stops working immediately, and so does every token delegated from it. This cannot be undone; the agent must request a new task.</p>
            <label className="mt-3 block text-xs text-ink-500">Reason (audited)<input className="mt-1 w-full" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. suspected misuse" /></label>
            <div className="mt-4 flex justify-end gap-2"><Button variant="ghost" onClick={() => setTarget(null)}>Cancel</Button>
              <Button variant="danger" onClick={revoke} disabled={reason.trim().length < 3}>Revoke token</Button></div>
          </div>
        </div>)}
    </>
  );
}
