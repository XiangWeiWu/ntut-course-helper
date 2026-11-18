import { useEffect, useState } from "react";
import { get, type Course } from "../api";

export type Crowd = { scenarios: { alpha: number; ratio: Record<string, number>; best_round?: number;
  history: { round: number; overloaded: number; excess_seats: number }[] }[] };
let cache: Promise<Crowd | null> | null = null;
export const useCrowd = () => {
  const [c, setC] = useState<Crowd | null>(null);
  useEffect(() => { (cache ||= get<Crowd>("/api/crowd").catch(() => null)).then(setC); }, []);
  return c;
};
export const scenarioOf = (c: Crowd | null, alpha: number) =>
  c?.scenarios.reduce((a, x) => (Math.abs(x.alpha - alpha) < Math.abs(a.alpha - alpha) ? x : a));

/** 每門課的搶課風險：在「alpha 比例的同學照推薦選」的模擬中，該開課班的需求／可用名額 */
export default function CrowdRisk({ courses, alpha, crowd, summary = true }: { courses: Course[]; alpha: number; crowd: Crowd | null; summary?: boolean }) {
  const sc = scenarioOf(crowd, alpha);
  if (!sc) return null;
  const rows = courses.map((c) => ({ c, r: sc.ratio[c.id] })).filter((x) => x.r !== undefined);
  const lvl = (r: number) => r > 1 ? ["var(--critical)", "可能額滿"] : r > 0.8 ? ["var(--serious)", "接近滿額"] : ["var(--good)", "名額充足"];
  const h0 = sc.history[0], h1 = sc.history[sc.best_round ?? sc.history.length - 1];
  return (
    <div style={{ marginTop: 6 }}>
      <div className="row" style={{ gap: 6 }}>
        <span className="muted">搶課風險（假設 {Math.round(sc.alpha * 100)}% 同學照推薦選）：</span>
        {rows.length ? rows.map(({ c, r }) => {
          const [col, label] = lvl(r);
          return <span key={c.id} className="status" title={`需求／可用名額 = ${r >= 99 ? "名額已被佔滿" : r.toFixed(2)}`}>
            <i style={{ background: col }} />{c.name} {label}</span>;
        }) : <span className="muted">這些課在模擬中沒有其他人被推薦，風險低</span>}
      </div>
      {summary && <p className="muted" style={{ margin: "2px 0 0" }}>全校模擬：推薦分散前 {h0.overloaded} 個開課班超額（{h0.excess_seats} 人次），
        用擁擠扣分分散後剩 {h1.overloaded} 個（{h1.excess_seats} 人次）。名額為推估值；不照推薦的同學依本學期實際人數佔用名額。</p>}
    </div>
  );
}
