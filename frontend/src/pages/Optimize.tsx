import { useEffect, useState } from "react";
import { get } from "../api";

type Eval = { objective: number; retake_score: number; retake_pairs: number; same_grade_pairs: number; teacher_violations: number;
  room_violations: number; class_required_conflicts: number; moved_periods: number;
  class_load_excess: number; class_load: { class: string; grade: number; consec_excess: number; daily_excess: number; worst: number; max_day: number }[]; upper_affected: Record<string, string> };
type Move = { ids: string[]; name: string; teachers: string[]; rooms: string[]; grade: number; required: boolean; from: string; to: string };
type Conf = { upper: string; upper_grade: number; upper_required: boolean; upper_time: string; lower: string; lower_grade: number;
  lower_time: string; risk: number; alternatives: number; weight: number };
type Cohort = { grade: number; cohort: number; standard: string | null; note?: string; required?: number; credits?: number;
  missing?: { name: string; elsewhere: boolean }[]; clashes?: string[]; graduation_credits?: string };
type Risk = { name: string; grade: number; teachers: string[]; alternatives: number; risk: number; course_rate: number; teacher_rate: number };
type Report = { dept: string; scenario: string; status: string; seconds: number; units: number; movable: number; shared_fixed: number;
  model_objective: number; checker_objective: number; before: Eval; after: Eval; moves: Move[];
  conflicts_before: Conf[]; conflicts_after: Conf[]; cohorts: Cohort[]; cohorts_before: Cohort[]; risk: Risk[];
  lower_required_occupancy: Record<string, { occupied: number; total: number }> };
type SumRow = { dept: string } & Record<"A" | "B", { status: string; retake_before: number; retake_after: number; pairs_before: number;
  pairs_after: number; moves: number; new_conflicts: number; missing: number; model: number; checker: number;
  load_before: number; load_after: number }>;

const pct = (a: number, b: number) => (b ? `${Math.round((1 - a / b) * 100)}%` : "—");
const Dot = ({ ok, label }: { ok: boolean; label: string }) => (
  <span className="status"><i style={{ background: ok ? "var(--good)" : "var(--critical)" }} />{label}</span>
);

export default function Optimize() {
  const [summary, setSummary] = useState<SumRow[]>([]);
  const [dept, setDept] = useState("資工");
  const [sc, setSc] = useState<"A" | "B">("A");
  const [r, setR] = useState<Report | null>(null);
  const [showBefore, setShowBefore] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { get<SumRow[]>("/api/timetable/summary").then(setSummary).catch((e) => setErr(String(e))); }, []);
  useEffect(() => {
    setR(null); setErr("");
    get<Report>(`/api/timetable/${encodeURIComponent(dept)}?scenario=${sc}`).then(setR).catch((e) => setErr(String(e)));
  }, [dept, sc]);

  const b = r?.before, a = r?.after;
  const conf = r ? (showBefore ? r.conflicts_before : r.conflicts_after) : [];
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card">
        <h2>系所排課最佳化：讓重修不衝堂、每屆都能準時畢業</h2>
        <p className="note">
          以 115-1 實際課表為起點，建議「搬動哪些課到哪個時段」，讓<b>高年級的課盡量不和低年級必修衝堂</b>（被當的學生才能重修），
          同時保證<b>不新增教師撞期、教室撞期、同班必修衝堂</b>（現況已存在的重疊一律保留：資料無法區分排錯與刻意安排，例如設計工作室多位老師同時段分組、平行班同時開）。低年級必修依「重修風險」加權：課程與教師的歷年退選率（經收縮估計；退選≠被當，僅為代理指標），
          若全校另有其他時段開同名課（可改選他班），權重按時段數降低。
        </p>
        <div className="row">
          <label className="muted">系所 <select value={dept} onChange={(e) => setDept(e.target.value)}>
            {(summary.length ? summary.map((s) => s.dept) : [dept]).map((d) => <option key={d} value={d}>{d}</option>)}
          </select></label>
          <span className="muted">方案</span>
          <button className={`btn ${sc === "A" ? "primary" : ""}`} onClick={() => setSc("A")}>A 少改動</button>
          <button className={`btn ${sc === "B" ? "primary" : ""}`} onClick={() => setSc("B")}>B 大改動</button>
          <span className="muted">A：一年級必修與跨系共用課不動；B：本系非共用課都可搬。</span>
        </div>
        {err && <p className="err">{err}</p>}
        {!r && !err && <p className="muted">載入中…</p>}
        {r && b && a && <>
          <div>
            <span className="stat"><div className="v">{b.retake_score} → {a.retake_score}</div><div className="k">加權重修衝堂分數（降低 {pct(a.retake_score, b.retake_score)}）</div></span>
            <span className="stat"><div className="v">{b.retake_pairs} → {a.retake_pairs}</div><div className="k">高年級課 × 低年級必修 衝堂組數</div></span>
            <span className="stat"><div className="v">{b.class_load_excess ?? "—"} → {a.class_load_excess ?? "—"}</div><div className="k">各班每日負擔超出節數（連續 &gt;3 節、每天 &gt;6 節）</div></span>
            <span className="stat"><div className="v">{r.moves.length}</div><div className="k">建議搬動的課（共 {a.moved_periods} 節次改變）</div></span>
          </div>
          <div className="row">
            <Dot ok={a.teacher_violations === 0} label={`新增教師撞期 ${a.teacher_violations}`} />
            <Dot ok={a.room_violations === 0} label={`新增教室撞期 ${a.room_violations}`} />
            <Dot ok={a.class_required_conflicts === 0} label={`新增同班必修衝堂 ${a.class_required_conflicts}`} />
            <Dot ok={Math.abs(r.model_objective - r.checker_objective) < 0.1} label={`交叉驗證：模型 ${r.model_objective}／獨立檢查 ${r.checker_objective}`} />
            <span className="muted">求解 {r.status === "OPTIMAL" ? "已證明最佳" : "20 秒內找到的最佳可行解（未證明最佳）"} · {r.seconds}s · 本系 {r.units} 個場次，可搬 {r.movable}、共用固定 {r.shared_fixed}</span>
          </div>
          <h3>受影響的高年級課（與任一低年級必修衝堂 / 該年級課數）</h3>
          <table><thead><tr><th>年級</th><th className="num">現況</th><th className="num">最佳化後</th><th className="num">1～(g−1) 年級必修佔用平日 1–9 節</th></tr></thead>
            <tbody>{Object.keys(a.upper_affected).map((g) => {
              const o = r.lower_required_occupancy[g];
              return <tr key={g}><td>{g} 年級</td><td className="num">{b.upper_affected[g]}</td><td className="num">{a.upper_affected[g]}</td>
                <td className="num">{o ? `${o.occupied}/${o.total} 節（${Math.round(o.occupied / o.total * 100)}%）` : "—"}</td></tr>;
            })}</tbody></table>
          <p className="muted">結構性限制：低年級必修若已佔滿大部分平日日間節次，任何排法都無法讓所有高年級課完全避開；
            剩下的衝堂需要靠「同名課在其他時段另開一班」、夜間或週六時段，或調整課程標準的學期安排來解決。</p>
        </>}
      </section>

      {r && b && a && <section className="card">
        <h2>各班每日負擔（開給該班的所有課，時段合併計算）</h2>
        <p className="muted">把「開給該班的所有課」的時段合起來，看成該班學生可能面對的最重負擔：連續超過 3 節沒有空堂、或一天超過 6 節的部分算「超出」。
          依據：連續上課造成認知疲勞，且對學習較弱的學生影響最大（Williams &amp; Shapiro, 2018；Sievertsen 等, 2016）。最佳化時以扣分方式盡量減少，優先順序低於重修衝堂。</p>
        <div className="scroll"><table><thead><tr><th>班級</th><th className="num">現況 連續超出</th><th className="num">現況 每日超出</th><th className="num">最佳化後 連續超出</th><th className="num">最佳化後 每日超出</th><th className="num">最長連續（後）</th><th className="num">最多一天（後）</th></tr></thead>
          <tbody>{[...new Set([...(b.class_load ?? []), ...(a.class_load ?? [])].map((x) => x.class))].sort().map((k) => {
            const x = (b.class_load ?? []).find((y) => y.class === k), y = (a.class_load ?? []).find((z) => z.class === k);
            return <tr key={k}><td>{k}</td><td className="num">{x?.consec_excess ?? 0}</td><td className="num">{x?.daily_excess ?? 0}</td>
              <td className="num">{y?.consec_excess ?? 0}</td><td className="num">{y?.daily_excess ?? 0}</td>
              <td className="num">{y ? `${y.worst} 節` : "—"}</td><td className="num">{y ? `${y.max_day} 節` : "—"}</td></tr>;
          })}</tbody></table></div>
        <p className="muted">方案 A 不搬一年級必修，所以一年級的負擔不會改變；方案 B 才會調整。</p>
      </section>}

      {r && <section className="card">
        <h2>各屆課程標準檢查（115-1，第 g 年級＝{115}−g+1 學年入學）</h2>
        <div className="scroll"><table><thead><tr><th>年級</th><th>入學年</th><th>適用標準</th><th className="num">本學期必修</th><th>本班未開（其他班有開？）</th><th>同班必修衝堂（最佳化後）</th></tr></thead>
          <tbody>{r.cohorts.map((c, i) => <tr key={i}>
            <td>{c.grade}</td><td>{c.cohort}</td><td>{c.standard ?? <span className="muted">{c.note}</span>}</td>
            <td className="num">{c.required ?? "—"}{c.credits ? ` 門／${c.credits} 學分` : ""}</td>
            <td>{c.missing?.length ? c.missing.map((m) => <div key={m.name}>{m.name} <span className="muted">{m.elsewhere ? "（其他班有開）" : "（全校查無同名課）"}</span></div>) : <span className="muted">無</span>}</td>
            <td>{c.clashes?.length ? c.clashes.join("、") : <Dot ok label="無" />}</td>
          </tr>)}</tbody></table></div>
        <p className="muted">以課名比對課程標準與實際開課。「全校查無同名課」可能是改名或該學期未開，系辦應確認該屆學生能否準時修到。</p>
      </section>}

      {r && <section className="card">
        <h2>建議搬動（{r.moves.length} 門）</h2>
        {r.moves.length ? <div className="scroll"><table><thead><tr><th>課程</th><th>年級</th><th>教師</th><th>教室</th><th>原時段</th><th>建議時段</th></tr></thead>
          <tbody>{r.moves.map((m) => <tr key={m.ids.join()}><td>{m.name} <span className="muted">{m.required ? "必修" : "選修"} {m.ids.join("/")}</span></td>
            <td>{m.grade}</td><td>{m.teachers.join("、")}</td><td className="muted">{m.rooms.join("、")}</td><td>{m.from}</td><td><b>{m.to}</b></td></tr>)}</tbody></table></div>
          : <p className="muted">現況已是此方案下的最佳排法。</p>}
        <p className="muted">建議時段已避開該教師在全校其他課、該教室（單一教室的課）的既有時段。實際採用前仍需與授課教師確認。</p>
      </section>}

      {r && <section className="card">
        <h2>衝堂明細：高年級課 × 低年級必修</h2>
        <div className="row">
          <button className={`btn ${!showBefore ? "primary" : ""}`} onClick={() => setShowBefore(false)}>最佳化後（{r.conflicts_after.length}）</button>
          <button className={`btn ${showBefore ? "primary" : ""}`} onClick={() => setShowBefore(true)}>現況（{r.conflicts_before.length}）</button>
          <span className="muted">依權重排序，最多顯示 40 筆</span>
        </div>
        <div className="scroll"><table><thead><tr><th>高年級課</th><th>時段</th><th>低年級必修</th><th>時段</th><th className="num">重修風險</th><th className="num">他班時段數</th><th className="num">權重</th></tr></thead>
          <tbody>{conf.map((c, i) => <tr key={i}><td>{c.upper} <span className="muted">{c.upper_grade}年級{c.upper_required ? "必修" : "選修"}</span></td><td>{c.upper_time}</td>
            <td>{c.lower} <span className="muted">{c.lower_grade}年級</span></td><td>{c.lower_time}</td><td className="num">{c.risk.toFixed(2)}</td>
            <td className="num">{c.alternatives}</td><td className="num">{c.weight.toFixed(2)}</td></tr>)}</tbody></table></div>
        <p className="muted">權重 = (高年級課為必修 ×2／選修 ×1) × 重修風險 ÷ 他班時段數。</p>
      </section>}

      {r && <section className="card">
        <h2>低年級必修的重修風險</h2>
        <div className="scroll"><table><thead><tr><th>課程</th><th>年級</th><th>教師</th><th className="num">課程退選率</th><th className="num">教師退選率</th><th className="num">他班時段數</th><th className="num">風險</th></tr></thead>
          <tbody>{r.risk.filter((x) => x.grade <= 3).slice(0, 25).map((x, i) => <tr key={i}><td>{x.name}</td><td>{x.grade}</td><td>{x.teachers.join("、")}</td>
            <td className="num">{(x.course_rate * 100).toFixed(1)}%</td><td className="num">{(x.teacher_rate * 100).toFixed(1)}%</td>
            <td className="num">{x.alternatives}</td><td className="num">{x.risk.toFixed(2)}</td></tr>)}</tbody></table></div>
        <p className="muted">風險 = 1 + 0.5×min(課程退選率/全校平均, 4) + 0.5×min(教師退選率/全校平均, 4)；退選率以 50 人先驗收縮到全校平均，避免小班極端值。</p>
      </section>}

      {summary.length > 0 && <section className="card">
        <h2>全校總覽：加權重修衝堂分數與班級負擔</h2>
        <div className="scroll"><table><thead><tr><th>系所</th><th className="num">現況</th><th className="num">A 少改動</th><th className="num">A 搬動</th><th className="num">B 大改動</th><th className="num">B 搬動</th><th className="num">負擔超出（現況→A→B）</th><th className="num">標準缺開</th><th>新增衝突</th><th>交叉驗證</th></tr></thead>
          <tbody>{summary.map((s) => <tr key={s.dept} onClick={() => setDept(s.dept)} style={{ cursor: "pointer" }}>
            <td>{s.dept}</td><td className="num">{s.A.retake_before}</td>
            <td className="num">{s.A.retake_after} {s.A.retake_before ? <span className="muted">(−{pct(s.A.retake_after, s.A.retake_before)})</span> : null}</td><td className="num">{s.A.moves}</td>
            <td className="num">{s.B.retake_after} {s.B.retake_before ? <span className="muted">(−{pct(s.B.retake_after, s.B.retake_before)})</span> : null}</td><td className="num">{s.B.moves}</td>
            <td className="num">{s.A.load_before ?? "—"} → {s.A.load_after ?? "—"} → {s.B.load_after ?? "—"}</td>
            <td className="num">{s.A.missing}</td>
            <td>{s.A.new_conflicts === 0 && s.B.new_conflicts === 0 ? <Dot ok label="0" /> : <Dot ok={false} label={`${s.A.new_conflicts + s.B.new_conflicts}`} />}</td>
            <td>{Math.abs(s.A.model - s.A.checker) < 0.1 && Math.abs(s.B.model - s.B.checker) < 0.1 ? <Dot ok label="一致" /> : <Dot ok={false} label="不一致" />}</td>
          </tr>)}</tbody></table></div>
        <p className="muted">點任一列可查看該系細節。</p>
      </section>}
    </div>
  );
}
