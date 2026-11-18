import { useState } from "react";
import type { Node } from "../prereq";

export type MapStatus = "passed" | "failed" | "current" | "future" | "affected";
const SEMS = [1, 2, 3, 4].flatMap((y) => [1, 2].map((s) => ({ y, s, label: `大${"一二三四"[y - 1]}${s === 1 ? "上" : "下"}` })));
const REQ = ["○", "△", "●", "▲"];
const COLOR: Record<MapStatus, string> = {
  passed: "var(--good)", failed: "var(--critical)", current: "var(--accent)", future: "var(--text-muted)", affected: "var(--serious)",
};
const LABEL: Record<MapStatus, string> = { passed: "已通過", failed: "被當／未修", current: "本學期", future: "未來", affected: "受先修影響" };

export const dimLabel = (name: string) =>
  name.startsWith("學院指定向度-") ? `通識：${name.slice(7)}` : name === "學生自選向度" ? "通識：不分向度" : name;

/** 課程地圖：學年 × 學期。點以前學期的必修切換通過／被當；選修預設收合，點開可勾選已修。 */
export default function CourseMap({ nodes, statusOf, onToggleRequired, electivesDone, onToggleElective }: {
  nodes: Node[]; statusOf: (key: string) => MapStatus; onToggleRequired: (key: string) => void;
  electivesDone: Set<string>; onToggleElective: (key: string) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <div>
      <div className="legend">{(Object.keys(LABEL) as MapStatus[]).map((k) =>
        <span key={k}><i style={{ background: COLOR[k] }} />{LABEL[k]}</span>)}</div>
      <div className="scroll">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(8, minmax(150px, 1fr))", gap: 8, minWidth: 1240 }}>
          {SEMS.map(({ y, s, label }) => {
            const here = nodes.filter((n) => n.year === y && n.sem === s);
            const req = here.filter((n) => REQ.includes(n.type));
            const ele = here.filter((n) => !REQ.includes(n.type));
            const k = `${y}-${s}`;
            const done = ele.filter((n) => electivesDone.has(n.key));
            return (
              <div key={k} style={{ background: "var(--surface-2)", borderRadius: 8, padding: 6 }}>
                <div style={{ fontWeight: 650, marginBottom: 4 }}>{label} <span className="muted">{req.reduce((a, n) => a + n.credit, 0)} 學分</span></div>
                {req.map((n) => {
                  const st = statusOf(n.key);
                  const clickable = st === "passed" || st === "failed";
                  return (
                    <div key={n.key} onClick={() => clickable && onToggleRequired(n.key)}
                      title={`${n.name}（${n.type} ${n.credit} 學分）${clickable ? "：點一下切換通過／被當" : ""}`}
                      style={{ borderLeft: `4px solid ${COLOR[st]}`, background: "var(--surface-1)", borderRadius: 4, padding: "2px 6px", marginBottom: 3,
                        fontSize: 12, cursor: clickable ? "pointer" : "default", textDecoration: st === "failed" ? "line-through" : undefined }}>
                      {dimLabel(n.name)} <span className="muted">{n.credit}</span>
                    </div>
                  );
                })}
                {ele.length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <button className="btn" style={{ padding: "1px 6px", fontSize: 12, width: "100%" }} onClick={() => setOpen({ ...open, [k]: !open[k] })}>
                      {open[k] ? "▾" : "▸"} 選修 {ele.length} 門{done.length ? `（已修 ${done.length}）` : ""}
                    </button>
                    {open[k] && ele.map((n) => (
                      <label key={n.key} style={{ display: "flex", gap: 4, fontSize: 12, padding: "1px 0", alignItems: "flex-start" }}>
                        <input type="checkbox" checked={electivesDone.has(n.key)} onChange={() => onToggleElective(n.key)} />
                        <span>{n.name} <span className="muted">{n.type}{n.credit}</span></span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
