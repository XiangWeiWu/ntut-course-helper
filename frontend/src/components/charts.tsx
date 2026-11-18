import { useState, type ReactNode } from "react";

type Tip = { x: number; y: number; body: ReactNode } | null;
export function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const el = tip ? <div className="tooltip" style={{ left: tip.x + 12, top: tip.y + 12 }}>{tip.body}</div> : null;
  return { el, show: (e: React.MouseEvent, body: ReactNode) => setTip({ x: e.clientX, y: e.clientY, body }), hide: () => setTip(null) };
}

const W = 520, H = 220, M = { l: 44, r: 12, t: 12, b: 34 };

/** 單一系列長條圖（magnitude）：細長條、4px 圓角頂端、直接標示數值 */
export function BarChart({ data, yMax = 1, fmt = (v: number) => v.toFixed(2), unit = "" }:
  { data: { label: string; value: number }[]; yMax?: number; fmt?: (v: number) => string; unit?: string }) {
  const t = useTip();
  const iw = W - M.l - M.r, ih = H - M.t - M.b, bw = Math.min(48, iw / data.length - 12);
  const y = (v: number) => M.t + ih - (v / yMax) * ih;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * yMax);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img">
        {ticks.map((v) => (
          <g key={v}>
            <line x1={M.l} x2={W - M.r} y1={y(v)} y2={y(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={M.l - 6} y={y(v) + 4} fontSize={11} textAnchor="end" fill="var(--text-muted)">{fmt(v)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = M.l + (iw / data.length) * (i + 0.5), top = y(d.value), h = M.t + ih - top;
          return (
            <g key={d.label} onMouseMove={(e) => t.show(e, <><b>{d.label}</b><br />{fmt(d.value)}{unit}</>)} onMouseLeave={t.hide}>
              <rect x={cx - iw / data.length / 2} y={M.t} width={iw / data.length} height={ih} fill="transparent" />
              <path d={`M${cx - bw / 2},${M.t + ih} V${top + 4} q0,-4 4,-4 H${cx + bw / 2 - 4} q4,0 4,4 V${M.t + ih} Z`} fill="var(--series-1)" opacity={h > 0 ? 1 : 0} />
              <text x={cx} y={top - 5} fontSize={11} textAnchor="middle" fill="var(--text-secondary)">{fmt(d.value)}</text>
              <text x={cx} y={H - 12} fontSize={11} textAnchor="middle" fill="var(--text-secondary)">{d.label}</text>
            </g>
          );
        })}
      </svg>
      {t.el}
    </div>
  );
}

/** 折線圖（≤3 系列），十字準線 + tooltip；x 為數值 */
export function LineChart({ series, xLabel, yLabel, xFmt = String, yFmt = (v: number) => v.toFixed(2), logX = false }:
  { series: { name: string; color: string; points: { x: number; y: number }[] }[]; xLabel: string; yLabel: string;
    xFmt?: (v: number) => string; yFmt?: (v: number) => string; logX?: boolean }) {
  const t = useTip();
  const [hx, setHx] = useState<number | null>(null);
  const all = series.flatMap((s) => s.points);
  const xs = [...new Set(all.map((p) => p.x))].sort((a, b) => a - b);
  const tx = (v: number) => (logX ? Math.log(v) : v);
  const x0 = tx(xs[0]), x1 = tx(xs[xs.length - 1]);
  let y0 = Math.min(0, ...all.map((p) => p.y)), y1 = Math.max(...all.map((p) => p.y));
  if (y1 === y0) y1 = y0 + 1;
  y1 += (y1 - y0) * 0.08;
  const M = { l: 44, r: 12, t: 26, b: 34 };
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const X = (v: number) => M.l + ((tx(v) - x0) / (x1 - x0 || 1)) * iw;
  const Y = (v: number) => M.t + ih - ((v - y0) / (y1 - y0)) * ih;
  const yt = Array.from({ length: 5 }, (_, i) => y0 + ((y1 - y0) * i) / 4);
  const onMove = (e: React.MouseEvent<SVGRectElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * iw + M.l;
    const near = xs.reduce((a, b) => (Math.abs(X(b) - px) < Math.abs(X(a) - px) ? b : a));
    setHx(near);
    t.show(e, <><b>{xLabel}：{xFmt(near)}</b>{series.map((s) => {
      const p = s.points.find((q) => q.x === near);
      return p ? <div key={s.name}><i style={{ background: s.color, display: "inline-block", width: 8, height: 8, borderRadius: 4, marginRight: 4 }} />{s.name}：{yFmt(p.y)}</div> : null;
    })}</>);
  };
  return (
    <div>
      {series.length > 1 && <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img">
        {yt.map((v, i) => (
          <g key={i}>
            <line x1={M.l} x2={W - M.r} y1={Y(v)} y2={Y(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={M.l - 6} y={Y(v) + 4} fontSize={11} textAnchor="end" fill="var(--text-muted)">{yFmt(v)}</text>
          </g>
        ))}
        {xs.filter((_, i) => xs.length < 12 || i % Math.ceil(xs.length / 10) === 0).map((v) => (
          <text key={v} x={X(v)} y={H - 16} fontSize={11} textAnchor="middle" fill="var(--text-muted)">{xFmt(v)}</text>
        ))}
        <text x={W / 2} y={H - 2} fontSize={11} textAnchor="middle" fill="var(--text-secondary)">{xLabel}</text>
        <text x={4} y={12} fontSize={11} fill="var(--text-secondary)">{yLabel}</text>
        {hx !== null && <line x1={X(hx)} x2={X(hx)} y1={M.t} y2={M.t + ih} stroke="var(--text-muted)" strokeDasharray="3 3" />}
        {series.map((s) => (
          <g key={s.name}>
            <polyline fill="none" stroke={s.color} strokeWidth={2} points={s.points.map((p) => `${X(p.x)},${Y(p.y)}`).join(" ")} />
            {s.points.length < 20 && s.points.map((p) => <circle key={p.x} cx={X(p.x)} cy={Y(p.y)} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />)}
          </g>
        ))}
        <rect x={M.l} y={M.t} width={iw} height={ih} fill="transparent" onMouseMove={onMove} onMouseLeave={() => { setHx(null); t.hide(); }} />
      </svg>
      {t.el}
    </div>
  );
}

/** 連續量熱圖（單一色相 light→dark） */
export function Heatmap({ rows, cols, value, tip, rowLabel = (r: string) => r, colLabel = (c: string) => c }:
  { rows: string[]; cols: string[]; value: (r: string, c: string) => number; tip: (r: string, c: string) => ReactNode;
    rowLabel?: (r: string) => string; colLabel?: (c: string) => string }) {
  const t = useTip();
  const max = Math.max(1, ...rows.flatMap((r) => cols.map((c) => value(r, c))));
  const steps = ["var(--surface-2)", "var(--seq-100)", "var(--seq-250)", "var(--seq-400)", "var(--seq-550)", "var(--seq-700)"];
  const color = (v: number) => (v <= 0 ? steps[0] : steps[Math.min(5, 1 + Math.floor((v / max) * 4.999))]);
  const cw = 30, ch = 20, lw = 56;
  return (
    <div className="scroll">
      <svg width={lw + cols.length * cw} height={20 + rows.length * ch} role="img">
        {cols.map((c, j) => <text key={c} x={lw + j * cw + cw / 2} y={13} fontSize={11} textAnchor="middle" fill="var(--text-muted)">{colLabel(c)}</text>)}
        {rows.map((r, i) => (
          <g key={r}>
            <text x={lw - 6} y={20 + i * ch + 14} fontSize={11} textAnchor="end" fill="var(--text-secondary)">{rowLabel(r)}</text>
            {cols.map((c, j) => (
              <rect key={c} x={lw + j * cw + 1} y={20 + i * ch + 1} width={cw - 2} height={ch - 2} rx={3} fill={color(value(r, c))}
                onMouseMove={(e) => t.show(e, tip(r, c))} onMouseLeave={t.hide} />
            ))}
          </g>
        ))}
      </svg>
      {t.el}
    </div>
  );
}
