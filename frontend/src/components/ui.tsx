import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { api } from "../services/api";

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try { setData(await api<T>(path)); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  }, [path]);
  useEffect(() => { void reload(); }, [reload]);
  return { data, error, loading, reload };
}

export function Card({ title, actions, children, className = "", icon }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <section className={`glass rounded-2xl ${className}`}>
      {title && (
        <header className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-5 py-3.5">
          <h2 className="flex items-center gap-2 font-display text-[15px] font-semibold text-ink-100">{icon}{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const TONES = {
  ok: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
  warn: "bg-amber-400/10 text-amber-300 ring-amber-400/25",
  bad: "bg-rose-500/10 text-rose-300 ring-rose-500/25",
  info: "bg-cyan-400/10 text-cyan-300 ring-cyan-400/25",
  violet: "bg-violet-400/10 text-violet-300 ring-violet-400/25",
  muted: "bg-white/[0.04] text-ink-300 ring-white/10",
} as const;
export type Tone = keyof typeof TONES;

export function Badge({ tone = "muted", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${TONES[tone]}`}>{children}</span>;
}

export function Button({ variant = "primary", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "danger" }) {
  const v = {
    primary: "bg-gradient-to-r from-cyan-400 to-violet-400 text-ink-950 shadow-[0_8px_24px_-8px_rgb(34_211_238/.6)] hover:brightness-110",
    ghost: "border border-white/10 bg-white/[0.03] text-ink-100 hover:bg-white/[0.07] hover:border-white/20",
    danger: "bg-rose-500 text-white shadow-[0_8px_24px_-8px_rgb(244_63_94/.6)] hover:bg-rose-400",
  }[variant];
  return <button {...p} className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition active:scale-[.98] disabled:opacity-40 disabled:shadow-none disabled:active:scale-100 ${v} ${p.className ?? ""}`} />;
}

export function Loading({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-1" role="status" aria-label="Loading">
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-10 animate-pulse rounded-xl bg-white/[0.04]" style={{ opacity: 1 - i * 0.14 }} />
      ))}
    </div>
  );
}

export function Spinner() {
  return <Loader2 className="h-4 w-4 animate-spin" aria-hidden />;
}

type Toast = { id: number; ok: boolean; text: string };
let pushToast: (t: Omit<Toast, "id">) => void = () => {};
export const toast = { ok: (text: string) => pushToast({ ok: true, text }), err: (text: string) => pushToast({ ok: false, text }) };

export function Toaster() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    pushToast = (t) => {
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs, { ...t, id }]);
      setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 5000);
    };
    return () => { pushToast = () => {}; };
  }, []);
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-full max-w-sm flex-col gap-2" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} role="status" className={`glass pointer-events-auto animate-fade-in rounded-xl border-l-4 px-4 py-3 text-sm ${t.ok
          ? "border-l-emerald-400 text-emerald-100" : "border-l-rose-400 text-rose-100"}`}>{t.text}</div>
      ))}
    </div>
  );
}

export function useTitle(title: string) {
  useEffect(() => { document.title = `${title} · SENTRIX`; }, [title]);
}

export function ErrorBox({ message }: { message: string }) {
  return <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{message}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-ink-500">
      <Inbox className="h-6 w-6 text-ink-700" />{children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: string; subtitle?: string; actions?: ReactNode; eyebrow?: string }) {
  useTitle(title);
  return (
    <div className="mb-7 flex animate-fade-in flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="mb-1.5 text-[11px] font-semibold tracking-[0.2em] text-cyan-300/80 uppercase">{eyebrow}</div>}
        <h1 className="font-display text-2xl font-semibold text-ink-100 md:text-[28px]">{title}</h1>
        {subtitle && <p className="mt-1.5 max-w-3xl text-sm text-ink-300">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Stat({ label, value, hint, icon, accent = "cyan" }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; accent?: "cyan" | "violet" | "emerald" | "amber" }) {
  const ring = { cyan: "from-cyan-400/25", violet: "from-violet-400/25", emerald: "from-emerald-400/25", amber: "from-amber-400/25" }[accent];
  return (
    <div className="glass relative overflow-hidden rounded-2xl p-5">
      <div className={`pointer-events-none absolute -top-10 -right-10 h-28 w-28 rounded-full bg-gradient-to-br ${ring} to-transparent blur-2xl`} />
      <div className="flex items-center gap-2 text-[11px] font-medium tracking-wider text-ink-500 uppercase">{icon}{label}</div>
      <div className="mt-3 font-display text-3xl font-semibold tabular-nums text-ink-100">{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-500">{hint}</div>}
    </div>
  );
}

export const fmtTime = (iso: string) => new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z").toLocaleString();
