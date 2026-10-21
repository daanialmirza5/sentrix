import { useMemo, useRef, useState } from "react";
import type { DriftPoint, DriftReport, DriftSummary } from "../services/api";
import { Card, ErrorBox, Loading, PageHeader, useApi } from "../components/ui";

// Categorical slots 1-2 (dark steps), validated on #0f1625: CVD ΔE 26.8, contrast ≥ 3:1. Rolling is also dashed.
const C_FROZEN = "#3987e5";
const C_ROLLING = "#d95926";
const W = 760, H = 300, M = { t: 16, r: 92, b: 34, l: 48 };

/** Round tick step from the 1-2-5 sequence giving about 4-5 gridlines, and the axis max it implies. */
function niceScale(v: number) {
  const raw = Math.max(v, 1) / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw)!;
  return { step, max: Math.ceil(v / step) * step };
}

function Chart({ points, h, driftStart }: { points: DriftPoint[]; h: number; driftStart: number }) {
  const [hover, setHover] = useState<DriftPoint | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const xMin = points[0].window, xMax = points[points.length - 1].window;
  const { step, max: yMax } = niceScale(Math.max(h * 1.5, ...points.map((p) => Math.max(p.S, p.S_rolling))));
  const x = (w: number) => M.l + ((w - xMin) / Math.max(1, xMax - xMin)) * (W - M.l - M.r);
  const y = (v: number) => H - M.b - (v / yMax) * (H - M.t - M.b);
  const path = (k: "S" | "S_rolling") => points.map((p, i) => `${i ? "L" : "M"}${x(p.window).toFixed(1)},${y(p[k]).toFixed(1)}`).join("");
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step);
  const last = points[points.length - 1];

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const box = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const w = Math.round(xMin + ((px - M.l) / (W - M.l - M.r)) * (xMax - xMin));
    setHover(points.find((p) => p.window === Math.min(xMax, Math.max(xMin, w))) ?? null);
  }

  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" onMouseMove={onMove} onMouseLeave={() => setHover(null)}
        aria-label={`CUSUM statistic per window for frozen anchor and rolling baseline; threshold h=${h}`}>
        {ticks.map((t) => (
          <g key={t}><line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="#22304a" strokeWidth={1} />
            <text x={M.l - 8} y={y(t) + 4} textAnchor="end" fontSize={11} fill="#5b6b86">{Math.round(t)}</text></g>))}
        {driftStart >= xMin && driftStart <= xMax && (
          <g><line x1={x(driftStart)} x2={x(driftStart)} y1={M.t} y2={H - M.b} stroke="#5b6b86" strokeDasharray="2 4" />
            <text x={x(driftStart) + 6} y={M.t + 10} fontSize={11} fill="#a9b6cc">drift begins →</text></g>)}
        <line x1={M.l} x2={W - M.r} y1={y(h)} y2={y(h)} stroke="#a9b6cc" strokeWidth={1} strokeDasharray="6 4" />
        <text x={W - M.r + 6} y={y(h) + 4} fontSize={11} fill="#a9b6cc">h = {h}</text>
        <path d={path("S_rolling")} fill="none" stroke={C_ROLLING} strokeWidth={2} strokeDasharray="6 3" strokeLinejoin="round" />
        <path d={path("S")} fill="none" stroke={C_FROZEN} strokeWidth={2} strokeLinejoin="round" />
        <text x={x(last.window) + 6} y={Math.max(M.t + 8, y(last.S)) + 4} fontSize={11} fill="#e6ecf5">Frozen</text>
        <text x={x(last.window) + 6} y={Math.min(H - M.b, y(last.S_rolling) + (Math.abs(y(last.S) - y(last.S_rolling)) < 14 ? 14 : 0)) + 4} fontSize={11} fill="#e6ecf5">Rolling</text>
        {[xMin, Math.round((xMin + xMax) / 2), xMax].map((w) => (
          <text key={w} x={x(w)} y={H - M.b + 18} textAnchor="middle" fontSize={11} fill="#5b6b86">{w}</text>))}
        <text x={(M.l + W - M.r) / 2} y={H - 2} textAnchor="middle" fontSize={11} fill="#5b6b86">window (10 actions each)</text>
        {hover && (
          <g><line x1={x(hover.window)} x2={x(hover.window)} y1={M.t} y2={H - M.b} stroke="#a9b6cc" strokeWidth={1} />
            <circle cx={x(hover.window)} cy={y(hover.S)} r={4} fill={C_FROZEN} stroke="#0f1625" strokeWidth={2} />
            <circle cx={x(hover.window)} cy={y(hover.S_rolling)} r={4} fill={C_ROLLING} stroke="#0f1625" strokeWidth={2} /></g>)}
      </svg>
      {hover && (
        <div className="pointer-events-none absolute top-2 rounded-md border border-ink-700 bg-ink-950/95 px-3 py-2 text-xs shadow-lg"
          style={{ left: `${Math.min(70, (x(hover.window) / W) * 100)}%` }}>
          <div className="text-ink-300">Window {hover.window} · {hover.phase}</div>
          <div className="mt-1 flex items-center gap-2"><span className="h-0.5 w-3" style={{ background: C_FROZEN }} /><span className="text-ink-100">Frozen S {hover.S.toFixed(2)}</span></div>
          <div className="flex items-center gap-2"><span className="h-0.5 w-3 border-t-2 border-dashed" style={{ borderColor: C_ROLLING }} /><span className="text-ink-100">Rolling S {hover.S_rolling.toFixed(2)}</span></div>
        </div>)}
    </div>
  );
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export default function Drift() {
  const { data, error, loading } = useApi<DriftReport>("/v1/reports/drift");
  const [full, setFull] = useState(false);
  const view = useMemo(() => {
    if (!data) return [];
    const pts = data.trace.points, h = data.trace.h;
    if (full) return pts;
    const fz = pts.find((p) => p.phase === "drift" && p.S > h)?.window ?? pts.length;
    const rl = pts.find((p) => p.phase === "drift" && p.S_rolling > h)?.window ?? pts.length;
    return pts.filter((p) => p.window >= Math.max(1, data.trace.drift_starts_after_window - 10) && p.window <= Math.max(fz, rl) + 5);
  }, [data, full]);

  if (loading) return <Loading rows={6} />;
  if (error) return <ErrorBox message={error} />;
  const d = data!;
  const rows: [string, string, Record<"frozen" | "rolling", DriftSummary>][] = [
    ["Calibration (seeds 0–9)", "5", d.calibration_default_h5], ["Held-out (seeds 10–39)", "5", d.held_out_default_h5],
    ["Held-out (seeds 10–39)", String(d.calibrated_h), d.held_out_calibrated]];

  return (
    <>
      <PageHeader title="Drift monitoring" subtitle="Measured on the synthetic drift benchmark (scripts/eval_drift.py). Not production accuracy." />
      <Card title={`CUSUM S_t, held-out seed ${d.trace.seed} (first held-out seed, fixed choice)`} actions={
        <div className="flex rounded-md border border-ink-700 text-xs" role="group" aria-label="Range">
          <button onClick={() => setFull(false)} className={`px-3 py-1 ${!full ? "bg-ink-800 text-teal-300" : "text-ink-300"}`} aria-pressed={!full}>Alarm region</button>
          <button onClick={() => setFull(true)} className={`px-3 py-1 ${full ? "bg-ink-800 text-teal-300" : "text-ink-300"}`} aria-pressed={full}>Full run</button>
        </div>}>
        <div className="mb-3 flex flex-wrap gap-4 text-xs text-ink-300" aria-label="Legend">
          <span className="flex items-center gap-2"><span className="h-0.5 w-5" style={{ background: C_FROZEN }} />Frozen anchor</span>
          <span className="flex items-center gap-2"><span className="w-5 border-t-2 border-dashed" style={{ borderColor: C_ROLLING }} />Rolling baseline (EWMA α 0.15)</span>
          <span className="flex items-center gap-2"><span className="w-5 border-t border-dashed border-ink-300" />Alarm threshold h</span>
        </div>
        <Chart points={view} h={d.trace.h} driftStart={d.trace.drift_starts_after_window} />
        <p className="mt-3 text-xs text-ink-500">{d.description} CUSUM: S_t = max(0, S_(t-1) + x_t − k), k = {d.k}. h was calibrated on seeds 0–9 only.</p>
      </Card>
      <Card title="Results (table view)" className="mt-4">
        <div className="overflow-x-auto"><table>
          <thead><tr><th>Seed set</th><th>h</th><th>Detector</th><th className="text-right">Benign false alarms</th><th className="text-right">Detection rate</th><th className="text-right">Median delay (windows)</th></tr></thead>
          <tbody>{rows.flatMap(([set, h, s]) => (["frozen", "rolling"] as const).map((det) => (
            <tr key={set + h + det}><td>{set}</td><td className="font-mono">{h}</td>
              <td><span className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: det === "frozen" ? C_FROZEN : C_ROLLING }} />{det}</span></td>
              <td className="text-right font-mono tabular-nums">{pct(s[det].benign_false_alarm_rate)}</td>
              <td className="text-right font-mono tabular-nums">{pct(s[det].detection_rate)}</td>
              <td className="text-right font-mono tabular-nums">{s[det].median_delay_windows ?? "—"}</td></tr>)))}</tbody>
        </table></div>
        <p className="mt-3 text-xs text-amber-200/90">Reading: at h = {d.calibrated_h} the frozen anchor's median delay is {d.held_out_calibrated.frozen.median_delay_windows ?? "—"} windows
          vs {d.held_out_calibrated.rolling.median_delay_windows ?? "—"} for the rolling baseline; {pct(d.held_out_calibrated.frozen.benign_false_alarm_rate)} of
          held-out benign runs still false-alarm. The drift engine is not yet fed by live traffic.</p>
      </Card>
    </>
  );
}
