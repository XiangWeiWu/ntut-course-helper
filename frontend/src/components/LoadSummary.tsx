import { slotKeys, type Course } from "../api";
import { loadExcess } from "../load";

const DAY_ZH: Record<string, string> = { mon: "一", tue: "二", wed: "三", thu: "四", fri: "五", sat: "六", sun: "日" };

/** 每天的節數與最長連續節數；超過上限以紅色標示（定義見 load.ts） */
export default function LoadSummary({ courses, maxConsec, maxDaily }: { courses: Course[]; maxConsec: number; maxDaily: number }) {
  const e = loadExcess(new Set(courses.flatMap(slotKeys)), { maxConsec, maxDaily, weight: 0 });
  const days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].filter((d) => e.per_day[d] > 0 || ["mon", "tue", "wed", "thu", "fri"].includes(d));
  const bad = (d: string) => e.per_day[d] > maxDaily || e.longest_run[d] > maxConsec;
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className="muted">每日負擔：</span>
      {days.map((d) => (
        <span key={d} className="tag" style={bad(d) ? { background: "var(--conflict-bg)", color: "var(--text-primary)" } : undefined}
          title={`週${DAY_ZH[d]}：${e.per_day[d]} 節，最長連續 ${e.longest_run[d]} 節`}>
          週{DAY_ZH[d]} {e.per_day[d]} 節／連 {e.longest_run[d]}
        </span>
      ))}
      {e.consec_excess + e.daily_excess === 0
        ? <span className="status"><i style={{ background: "var(--good)" }} />沒有超過上限</span>
        : <span className="status"><i style={{ background: "var(--serious)" }} />連續超出 {e.consec_excess} 節、每日超出 {e.daily_excess} 節</span>}
    </div>
  );
}
