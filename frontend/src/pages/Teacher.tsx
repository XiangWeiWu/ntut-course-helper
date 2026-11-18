import { useEffect, useState } from "react";
import { DAY_ZH, PERIODS, STATIC, get, post } from "../api";
import { Heatmap } from "../components/charts";

type Row = { id: string; name: string; capacity: number; demand: number; enrolled: number; oversub: number;
  full_at: number | null; teachers: string[]; observed: number; capacitySource: string; advice: string };
type Cell = { grade: number; day: string; period: string; required: number; electives: string[] };

const SRC: Record<string, string> = { teacher: "師", notes: "註", ceiling: "頂" };
const statusOf = (o: number) => o >= 1.5 ? ["var(--critical)", "嚴重超額"] : o >= 1 ? ["var(--serious)", "滿額"] : o < 0.4 ? ["var(--warning)", "需求低"] : ["var(--good)", "平衡"];

export default function Teacher() {
  const [teacher, setTeacher] = useState("");
  const [dept, setDept] = useState("資工");
  const [rows, setRows] = useState<Row[]>([]);
  const [cells, setCells] = useState<Cell[]>([]);
  const [err, setErr] = useState("");
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const saveCap = async (r: Row) => {
    const v = parseInt(edit[r.id] ?? "", 10);
    if (!(v > 0)) return;
    try {
      const res = await post<{ capacity: number; capacitySource: string }>("/api/capacity", { course_id: r.id, capacity: v });
      setRows(rows.map((x) => x.id === r.id ? { ...x, capacity: res.capacity, capacitySource: res.capacitySource, oversub: x.demand / res.capacity } : x));
      setMsg(STATIC ? `已在「這台瀏覽器」把「${r.name}」名額設為 ${res.capacity}（線上版無法集中收集，其他人看不到）`
        : `已更新「${r.name}」名額為 ${res.capacity}（下學期同課號同教師自動沿用）`);
    } catch (e) { setErr(String(e)); }
  };
  const load = () => {
    setErr("");
    get<Row[]>(`/api/teacher/demand?${new URLSearchParams({ teacher, dept: teacher ? "" : dept })}`).then(setRows).catch((e) => setErr(String(e)));
    if (dept) get<Cell[]>(`/api/dept/conflicts?dept=${encodeURIComponent(dept)}`).then(setCells).catch(() => setCells([]));
  };
  useEffect(load, []); // eslint-disable-line
  const grades = [...new Set(cells.map((c) => c.grade))].sort();
  const days = ["mon", "tue", "wed", "thu", "fri"];
  const cols = days.flatMap((d) => PERIODS.slice(0, 10).map((p) => `${d}|${p}`));
  const find = (g: string, k: string) => cells.find((c) => `${c.grade}` === g && `${c.day}|${c.period}` === k);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card">
        <h2>課程需求預測（模擬）</h2>
        <div className="row">
          <input placeholder="教師姓名" value={teacher} onChange={(e) => setTeacher(e.target.value)} />
          <span className="muted">或</span>
          <input placeholder="系所簡稱（如 資工、電機、工管）" value={dept} onChange={(e) => setDept(e.target.value)} />
          <button className="btn primary" onClick={load}>查詢</button>
        </div>
        <p className="note">「模擬需求」= 不受名額限制時想選此課的模擬學生數（大學部本班學生，校準至 115-1 實際人數）。
          名額多為推估值（資料無人數上限欄位）；<b>授課教師可在右側回報實際名額</b>，系統會立即採用。滿額課的真實需求只知下界，因此需求多為保守估計。</p>
        {err && <p className="err">{err}</p>}
        <div className="scroll">
          <table>
            <thead><tr><th>課程</th><th>教師</th><th className="num">模擬需求</th><th className="num">名額(推估)</th><th className="num">需求/名額</th><th className="num">實際選課</th><th>狀態</th><th>建議</th><th>回報實際名額</th></tr></thead>
            <tbody>
              {rows.map((r) => {
                const [col, label] = statusOf(r.oversub);
                return (
                  <tr key={r.id}>
                    <td>{r.name} <span className="muted">{r.id}</span></td><td>{r.teachers.join("、")}</td>
                    <td className="num">{r.demand}</td><td className="num">{r.capacity}<span className="muted"> {SRC[r.capacitySource] ?? "*"}</span></td>
                    <td className="num">{r.oversub.toFixed(2)}</td><td className="num">{r.observed}</td>
                    <td><span className="status"><i style={{ background: col }} />{label}</span></td><td className="muted">{r.advice}</td>
                    <td><input type="number" min={1} placeholder="人數" value={edit[r.id] ?? ""} style={{ width: 64 }}
                      onChange={(e) => setEdit({ ...edit, [r.id]: e.target.value })} onKeyDown={(e) => e.key === "Enter" && saveCap(r)} />
                      <button className="btn" onClick={() => saveCap(r)}>送出</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {msg && <p className="status"><i style={{ background: "var(--good)" }} />{msg}</p>}
        <p className="muted">名額來源：「師」教師回報、「註」課程備註、「頂」近 5 年同課同師人數反覆達到的天花板（已用備註上限校正加簽偏誤）、「*」教室／歷史最大人數（低可信度）。只列出可搶的選修課。</p>
      </section>
      {dept && !teacher && (
        <section className="card">
          <h2>{dept}：各年級必修占用節次（週一～週五）</h2>
          <p className="muted">顏色越深＝該年級在此節次的必修越多。若本系選修開在深色格，同年級學生幾乎無法修。滑過格子看細節。</p>
          {grades.length ? (
            <Heatmap rows={grades.map(String)} cols={cols} rowLabel={(g) => `${g} 年級`}
              colLabel={(c) => { const [d, p] = c.split("|"); return p === "1" ? DAY_ZH[d] + "1" : p; }}
              value={(g, k) => find(g, k)?.required ?? 0}
              tip={(g, k) => { const c = find(g, k); const [d, p] = k.split("|");
                return <><b>{g} 年級 週{DAY_ZH[d]} 第{p}節</b><br />必修 {c?.required ?? 0} 門
                  {c?.electives.length ? <><br />同時段本系選修：{c.electives.slice(0, 4).join("、")}</> : null}</>; }} />
          ) : <p className="muted">查無資料</p>}
        </section>
      )}
    </div>
  );
}
