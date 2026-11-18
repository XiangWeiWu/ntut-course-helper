import type { Edge, Node } from "../prereq";
import type { MapStatus } from "./CourseMap";
import { useTip } from "./charts";

const COLOR: Record<MapStatus, string> = {
  passed: "var(--good)", failed: "var(--critical)", current: "var(--accent)", future: "var(--text-muted)", affected: "var(--serious)",
};
const KIND: Record<Edge["kind"], string> = { series: "系列課", same: "上下學期同名", manual: "系所補充" };

/** 先修樹狀圖：欄＝學期（大一上…大四下），只畫有先修關係的課；被當的課往下游標示受影響。 */
export default function PrereqTree({ nodes, edges, statusOf }: { nodes: Node[]; edges: Edge[]; statusOf: (k: string) => MapStatus }) {
  const t = useTip();
  const used = new Set(edges.flatMap((e) => [e.from, e.to]));
  const shown = nodes.filter((n) => used.has(n.key));
  if (!shown.length) return <p className="muted">這個課程標準沒有可辨識的先修關係。</p>;
  const col = (n: Node) => (n.year - 1) * 2 + (n.sem - 1);
  const W = 150, H = 30, PAD = 24;
  const rows: Record<number, Node[]> = {};
  for (const n of shown) (rows[col(n)] ||= []).push(n);
  const pos = new Map<string, { x: number; y: number }>();
  let maxRows = 0;
  for (const [c, list] of Object.entries(rows)) {
    list.sort((a, b) => a.name.localeCompare(b.name, "zh-Hant"));
    list.forEach((n, i) => pos.set(n.key, { x: PAD + +c * W, y: PAD + 18 + i * H }));
    maxRows = Math.max(maxRows, list.length);
  }
  const width = PAD * 2 + 8 * W, height = PAD * 2 + 18 + maxRows * H;
  const bw = W - 26;
  return (
    <div className="scroll">
      <svg width={width} height={height} role="img" aria-label="先修關係樹狀圖">
        <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L8,4 L0,8 z" fill="var(--text-muted)" /></marker></defs>
        {Array.from({ length: 8 }, (_, c) => (
          <text key={c} x={PAD + c * W + bw / 2} y={PAD} fontSize={12} textAnchor="middle" fill="var(--text-secondary)">
            大{"一二三四"[Math.floor(c / 2)]}{c % 2 ? "下" : "上"}</text>
        ))}
        {edges.map((e, i) => {
          const a = pos.get(e.from), b = pos.get(e.to);
          if (!a || !b) return null;
          const x1 = a.x + bw, y1 = a.y + 10, x2 = b.x, y2 = b.y + 10;
          const bad = statusOf(e.from) === "failed" || statusOf(e.from) === "affected";
          return <path key={i} d={`M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2 - 2},${y2}`} fill="none"
            stroke={bad ? "var(--critical)" : "var(--border)"} strokeWidth={bad ? 2 : 1.5} strokeDasharray={e.kind === "manual" ? "4 3" : undefined}
            markerEnd="url(#arr)" onMouseMove={(ev) => t.show(ev, `${KIND[e.kind]}`)} onMouseLeave={t.hide} />;
        })}
        {shown.map((n) => {
          const p = pos.get(n.key)!, st = statusOf(n.key);
          return (
            <g key={n.key} onMouseMove={(ev) => t.show(ev, <><b>{n.name}</b><br />{n.type} {n.credit} 學分</>)} onMouseLeave={t.hide}>
              <rect x={p.x} y={p.y} width={bw} height={20} rx={4} fill="var(--surface-1)" stroke={COLOR[st]} strokeWidth={2} />
              <text x={p.x + 6} y={p.y + 14} fontSize={11} fill="var(--text-primary)">{n.name.length > 9 ? n.name.slice(0, 9) + "…" : n.name}</text>
            </g>
          );
        })}
      </svg>
      {t.el}
      <p className="muted">實線＝系列課（(一)→(二)）或上下學期同名必修；虛線＝系所補充（data/prereq.json）。紅色箭頭＝前一門被當，後續課程可能受影響（擋修規定請以系上公告為準）。</p>
    </div>
  );
}
