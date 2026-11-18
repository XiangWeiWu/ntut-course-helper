import { useEffect, useState } from "react";
import { STATIC, get, post } from "../api";
import { SCENARIO_CHOICES } from "../static";
import { BarChart, LineChart } from "../components/charts";

type Agg = Record<string, { mean: number; ci95: [number, number] }>;
type Grp = { welfare: number; credit_fill: number; top1: number };
type Summ = { students: number; by_arrival: Record<string, Grp>; by_grade: Record<string, Grp>;
  by_other_dept_demand: Record<string, Grp>; visits_p50_p90: [number, number];
  server: Record<string, number>; timeline: { day: number; own_dept: number; other_dept: number; general: number }[] };
type Result = { config: any; aggregate: Agg; last_run: Summ; top_oversubscribed: any[] };
type Sens = { cross_dept?: number; mechanism: string; priority_days: number | null; p_approve: number | null; capacity_factor: number; welfare: number;
  welfare_other_dept: number; gini: number; arrival_spearman: number; top1: number; visits_p90: number; addsigned: number; released: number };
type Report = { main: Result; fcfs: Result | null; sensitivity: Sens[] | null; validation: any };

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const C = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];

function Stat({ a, k, label, f = pct }: { a: Agg; k: string; label: string; f?: (v: number) => string }) {
  if (!a[k]) return null;
  return <span className="stat"><div className="v">{f(a[k].mean)}</div><div className="k">{label}<br />95% 區間 {f(a[k].ci95[0])}–{f(a[k].ci95[1])}</div></span>;
}

function View({ r }: { r: Result }) {
  const a = r.aggregate, l = r.last_run, s = l.server, ntut = r.config.mechanism === "ntut";
  return (
    <>
      <div>
        <Stat a={a} k="welfare_mean" label="平均效用達成率" />
        <Stat a={a} k="top1_rate" label="拿到第一志願（有選修需求者）" />
        <Stat a={a} k="welfare_other_dept" label="想修他系課學生的效用達成率" />
        <Stat a={a} k="arrival_spearman" label="手速 vs 結果 ρ（越負越看手速）" f={(v) => v.toFixed(3)} />
        <Stat a={a} k="welfare_gini" label="Gini（不平等）" f={(v) => v.toFixed(3)} />
      </div>
      <p className="muted">
        模擬學生 {l.students} 人 · seeds {r.config.seeds.length} · 登入次數中位數 {l.visits_p50_p90[0]}、前10%學生 ≥ {l.visits_p50_p90[1]} 次
        {ntut && <> · 加簽 {s.seats_addsigned} 人次 · 退選釋出名額 {s.seats_released} 次 · 換課 {s.swaps} 次 · 取得課程時間中位數第 {Number(s.median_acquire_day).toFixed(1)} 天</>}
      </p>
      <div className="grid2">
        {ntut && l.timeline?.length ? (
          <div><h3>兩週內累積選上的座位數（依課程類型）</h3>
            <LineChart xLabel="選課第幾天" yLabel="座位數" xFmt={(v) => v.toFixed(0)} yFmt={(v) => v.toFixed(0)}
              series={[
                { name: "本系生選本系課", color: C[0], points: l.timeline.map((t) => ({ x: t.day, y: t.own_dept })) },
                { name: "外系生選他系課", color: C[1], points: l.timeline.map((t) => ({ x: t.day, y: t.other_dept })) },
                { name: "通識/博雅", color: C[2], points: l.timeline.map((t) => ({ x: t.day, y: t.general })) },
              ]} />
            <p className="muted">第 7 天外系課開放時，外系生的線才開始上升。</p>
          </div>
        ) : <div />}
        <div><h3>依第一次登入順序（五分位）的拿到第一志願比例</h3>
          <BarChart data={Object.entries(l.by_arrival).map(([k, v]) => ({ label: k, value: v.top1 }))} fmt={pct} /></div>
      </div>
      <div className="grid2">
        <div><h3>依年級</h3>
          <table><thead><tr><th>年級</th><th className="num">效用達成</th><th className="num">學分滿足</th><th className="num">第一志願</th></tr></thead>
            <tbody>{Object.entries(l.by_grade).map(([g, v]) => <tr key={g}><td>{g}</td><td className="num">{pct(v.welfare)}</td><td className="num">{pct(v.credit_fill)}</td><td className="num">{pct(v.top1)}</td></tr>)}</tbody></table></div>
        <div><h3>想不想修他系課</h3>
          <table><thead><tr><th>學生</th><th className="num">效用達成</th><th className="num">學分滿足</th><th className="num">第一志願</th></tr></thead>
            <tbody>{Object.entries(l.by_other_dept_demand).map(([g, v]) => <tr key={g}><td>{g}</td><td className="num">{pct(v.welfare)}</td><td className="num">{pct(v.credit_fill)}</td><td className="num">{pct(v.top1)}</td></tr>)}</tbody></table></div>
      </div>
      <h3>最超額的課</h3>
      <div className="scroll"><table><thead><tr><th>課程</th><th>教師</th><th className="num">需求</th><th className="num">名額</th><th className="num">最終人數</th><th className="num">加簽</th><th className="num">釋出</th><th>名額來源</th></tr></thead>
        <tbody>{r.top_oversubscribed.slice(0, 12).map((c) => <tr key={c.id}><td>{c.name}</td><td>{c.teachers}</td><td className="num">{c.demand}</td><td className="num">{c.capacity}</td><td className="num">{c.enrolled}</td><td className="num">{c.addsigned ?? "—"}</td><td className="num">{c.released ?? "—"}</td><td className="muted">{c.capacity_source}</td></tr>)}</tbody></table></div>
    </>
  );
}

export default function Sim() {
  const [rep, setRep] = useState<Report | null>(null);
  const [custom, setCustom] = useState<Result | null>(null);
  const [p, setP] = useState({ mechanism: "ntut", seeds: 2, priority_days: 7, p_request: 0.3, p_approve: STATIC ? 0.9 : 0.8, visits_per_day: 1.5, capacity_factor: 1, servers: 8 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { get<Report>("/api/sim/report").then(setRep).catch((e) => setErr(String(e))); }, []);
  const runSim = async () => { setBusy(true); setErr(""); try { setCustom(await post<Result>("/api/sim/run", p)); } catch (e) { setErr(String(e)); } finally { setBusy(false); } };
  const num = (k: keyof typeof p, label: string, step = 1) => (
    <label className="muted">{label} <input type="number" step={step} value={p[k] as number} onChange={(e) => setP({ ...p, [k]: +e.target.value })} style={{ width: 70 }} /></label>
  );
  const pick = (k: keyof typeof p, label: string, xs: number[]) => (
    <label className="muted">{label} <select value={p[k] as number} onChange={(e) => setP({ ...p, [k]: +e.target.value })}>
      {xs.map((x) => <option key={x} value={x}>{x}</option>)}</select></label>
  );
  const sens = rep?.sensitivity?.filter((s) => s.capacity_factor === 1 && s.cross_dept === undefined);
  const cross = rep?.sensitivity?.filter((s) => s.cross_dept !== undefined) ?? [];
  const v = rep?.validation;
  const cmp = rep && rep.fcfs ? [["北科制度（本系優先7天＋加簽＋退選釋出）", rep.main], ["純搶課 FCFS（一次開放、無加簽）", rep.fcfs]] as const : [];
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card">
        <h2>北科選課制度模擬：115-1 基準結果</h2>
        <p className="note">
          制度：第 1 週只有本系生能選本系課、通識第一天全校開放；第 2 週全校開放；先到先得；滿額可申請加簽（老師同意後 1–3 天生效，上限為名額 +23%，取自資料）；
          有人退選才釋出名額，其他學生要回來刷才拿得到。每位代理人是一位大學部學生，以隨機效用模型排序志願，拿到更喜歡的課時會退掉較不喜歡的課。
        </p>
        {err && <p className="err">{err}</p>}
        {rep ? <View r={rep.main} /> : <p className="muted">載入中…</p>}
      </section>
      {cmp.length > 0 && (
        <section className="card">
          <h2>制度比較</h2>
          <div className="scroll"><table><thead><tr><th>制度</th><th className="num">效用達成</th><th className="num">第一志願</th><th className="num">想修他系課者效用</th><th className="num">手速 ρ</th><th className="num">登入次數 p90</th></tr></thead>
            <tbody>{cmp.map(([n, r]) => <tr key={n}><td>{n}</td><td className="num">{pct(r.aggregate.welfare_mean.mean)}</td><td className="num">{pct(r.aggregate.top1_rate.mean)}</td>
              <td className="num">{pct(r.aggregate.welfare_other_dept?.mean ?? 1)}</td><td className="num">{r.aggregate.arrival_spearman.mean.toFixed(3)}</td><td className="num">{r.last_run.visits_p50_p90[1]}</td></tr>)}</tbody></table></div>
        </section>
      )}
      {sens && sens.length > 0 && (
        <section className="card">
          <h2>敏感度分析：本系優先 × 加簽同意率（名額 ×1.0，3 seeds）</h2>
          <div className="grid2">
            <div><h3>想修他系課學生的效用達成率</h3>
              <LineChart tight xLabel="老師加簽同意率" yLabel="效用達成" yFmt={pct} xFmt={(x) => x.toFixed(1)}
                series={[0, 7].map((d, i) => ({ name: d ? "本系優先 7 天" : "無本系優先", color: C[i], points: sens.filter((s) => s.priority_days === d).map((s) => ({ x: s.p_approve!, y: s.welfare_other_dept })) }))} /></div>
            <div><h3>前 10% 學生的登入次數（刷課的努力成本）</h3>
              <LineChart xLabel="老師加簽同意率" yLabel="登入次數" yFmt={(v) => v.toFixed(0)} xFmt={(x) => x.toFixed(1)}
                series={[0, 7].map((d, i) => ({ name: d ? "本系優先 7 天" : "無本系優先", color: C[i], points: sens.filter((s) => s.priority_days === d).map((s) => ({ x: s.p_approve!, y: s.visits_p90 })) }))} /></div>
          </div>
          <div className="scroll"><table><thead><tr><th>制度</th><th className="num">本系優先(天)</th><th className="num">加簽同意率</th><th className="num">效用達成</th><th className="num">想修他系課者</th><th className="num">手速 ρ</th><th className="num">第一志願</th><th className="num">登入p90</th><th className="num">加簽人次</th></tr></thead>
            <tbody>{sens.map((s, i) => <tr key={i}><td>{s.mechanism === "fcfs" ? "純搶課" : "北科"}</td><td className="num">{s.priority_days ?? "—"}</td><td className="num">{s.p_approve ?? "—"}</td><td className="num">{pct(s.welfare)}</td><td className="num">{pct(s.welfare_other_dept)}</td><td className="num">{s.arrival_spearman.toFixed(3)}</td><td className="num">{pct(s.top1)}</td><td className="num">{s.visits_p90}</td><td className="num">{s.addsigned}</td></tr>)}</tbody></table></div>
          <p className="muted">解讀：本系優先幾乎消除「手速」的影響（ρ≈0），本系生受益；代價是想修他系課的學生效用下降，且大量學生需要反覆登入刷退選名額。加簽能部分彌補。
            注意：各情境間的效用差距只有零點幾個百分點，模型整體的名額競爭偏弱（見下方驗證），方向比幅度可信。</p>
          {cross.length > 0 && <>
            <h3>關鍵假設：選他系課的額外成本（無資料可估，每個值都重新校準）</h3>
            <table><thead><tr><th className="num">跨系成本</th><th className="num">效用達成</th><th className="num">想修他系課者</th><th className="num">手速 ρ</th><th className="num">第一志願</th><th className="num">登入p90</th></tr></thead>
              <tbody>{cross.map((s) => <tr key={s.cross_dept}><td className="num">{s.cross_dept}{s.cross_dept === 1.5 ? "（預設）" : ""}</td><td className="num">{pct(s.welfare)}</td><td className="num">{pct(s.welfare_other_dept)}</td><td className="num">{s.arrival_spearman.toFixed(3)}</td><td className="num">{pct(s.top1)}</td><td className="num">{s.visits_p90}</td></tr>)}</tbody></table>
            <p className="muted">跨系成本 0 / 1.5 / 3 時，他系課約占選上座位的 38% / 22% / 10%。結論方向在三個值下一致。</p>
          </>}
        </section>
      )}
      {v && (
        <section className="card">
          <h2>模型驗證（hold-out）：{v.train.join("-")} 校準 → 預測 {v.test.join("-")} 各課人數</h2>
          <table><thead><tr><th>模型</th><th>範圍</th><th className="num">MAE（人）</th><th className="num">Spearman ρ</th></tr></thead>
            <tbody>
              <tr><td>代理人模擬</td><td>全部 {v.n_courses} 門</td><td className="num">{v.sim_all.MAE}</td><td className="num">{v.sim_all.spearman}</td></tr>
              <tr><td>代理人模擬</td><td>前學期開過的 {v.n_seen_before} 門</td><td className="num">{v.sim_seen.MAE}</td><td className="num">{v.sim_seen.spearman}</td></tr>
              <tr><td>基準：沿用上學期人數</td><td>前學期開過的 {v.n_seen_before} 門</td><td className="num">{v.baseline_seen.MAE}</td><td className="num">{v.baseline_seen.spearman}</td></tr>
            </tbody></table>
          <p className="muted">誠實結論：預測各課人數時，模擬明顯輸給「沿用上學期人數」。原因之一是校準用的歷史人數已被名額截斷，模型低估了真實的搶課競爭。
            它的用途是比較制度與參數的「方向」（反事實），不是預測人數。</p>
        </section>
      )}
      <section className="card">
        <h2>自訂情境</h2>
        <div className="row">
          <select value={p.mechanism} onChange={(e) => setP({ ...p, mechanism: e.target.value })}>
            <option value="ntut">北科制度</option><option value="fcfs">純搶課 FCFS</option>
          </select>
          {STATIC ? <>
            {p.mechanism === "ntut" && <>{pick("priority_days", "本系優先天數", SCENARIO_CHOICES.priority_days)}{pick("p_approve", "加簽同意率", SCENARIO_CHOICES.p_approve)}</>}
            {pick("capacity_factor", "名額×", SCENARIO_CHOICES.capacity_factor)}
          </> : <>
            {p.mechanism === "ntut" && <>{num("priority_days", "本系優先天數")}{num("p_approve", "加簽同意率", 0.1)}{num("p_request", "申請加簽率", 0.1)}{num("visits_per_day", "每日登入次數", 0.5)}</>}
            {num("capacity_factor", "名額×", 0.1)}{num("servers", "伺服器 worker")}{num("seeds", "seeds")}
          </>}
          <button className="btn primary" onClick={runSim} disabled={busy}>{busy ? "模擬中…" : STATIC ? "查看結果" : "執行"}</button>
        </div>
        {STATIC && <p className="muted">線上版顯示預先算好的 21 種情境（每種 3 個 seeds）。要輸入任意參數即時模擬，請依 README 在本機執行。</p>}
        {custom && <View r={custom} />}
      </section>
    </div>
  );
}
