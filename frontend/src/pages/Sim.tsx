import { useEffect, useState } from "react";
import { get, post } from "../api";
import { BarChart, LineChart } from "../components/charts";

type Agg = Record<string, { mean: number; ci95: [number, number] }>;
type Summ = { students: number; by_arrival: Record<string, { welfare: number; credit_fill: number; top1: number }>;
  by_grade: Record<string, { welfare: number; credit_fill: number; top1: number }>;
  server: Record<string, number>; queue_timeline: { t: number; requests: number; wait: number }[] };
type Result = { config: any; aggregate: Agg; last_run: Summ; top_oversubscribed: any[] };
type Sens = { servers: number; throughput_rps: number; capacity_factor: number; welfare: number; gini: number; arrival_spearman: number; top1: number; wait_p95: number; timeouts: number };
type Report = { main: Result; sensitivity: Sens[] | null; validation: any };

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

function View({ r }: { r: Result }) {
  const a = r.aggregate, l = r.last_run;
  const stat = (k: string, label: string, f = pct) => (
    <span className="stat"><div className="v">{f(a[k].mean)}</div><div className="k">{label}　95% 區間 {f(a[k].ci95[0])}–{f(a[k].ci95[1])}</div></span>
  );
  return (
    <>
      <div>
        {stat("welfare_mean", "平均效用達成率")}{stat("top1_rate", "拿到第一志願比例")}
        {stat("welfare_gini", "Gini（不平等）", (v) => v.toFixed(3))}{stat("arrival_spearman", "到達時間 vs 效用 ρ", (v) => v.toFixed(3))}
        {stat("full_courses", "滿額課程數", (v) => v.toFixed(0))}
      </div>
      <p className="muted">模擬學生 {l.students} 人 · seeds {r.config.seeds.length} · 吞吐 {l.server.throughput_rps} req/s · 等候 p95 {l.server.wait_p95}s · 逾時 {l.server.timeouts} 次</p>
      <div className="grid2">
        <div><h3>依到達順序（五分位）的拿到第一志願比例</h3>
          <BarChart data={Object.entries(l.by_arrival).map(([k, v]) => ({ label: k, value: v.top1 }))} fmt={pct} /></div>
        <div><h3>開放後每 5 秒的請求數</h3>
          <LineChart series={[{ name: "請求數", color: "var(--series-1)", points: l.queue_timeline.slice(0, 40).map((q) => ({ x: q.t, y: q.requests })) }]}
            xLabel="開放後秒數" yLabel="請求數" yFmt={(v) => v.toFixed(0)} /></div>
      </div>
      <h3>依年級</h3>
      <table><thead><tr><th>年級</th><th className="num">效用達成率</th><th className="num">學分滿足率</th><th className="num">第一志願</th></tr></thead>
        <tbody>{Object.entries(l.by_grade).map(([g, v]) => <tr key={g}><td>{g}</td><td className="num">{pct(v.welfare)}</td><td className="num">{pct(v.credit_fill)}</td><td className="num">{pct(v.top1)}</td></tr>)}</tbody></table>
      <h3>最超額的課</h3>
      <div className="scroll"><table><thead><tr><th>課程</th><th>教師</th><th className="num">需求</th><th className="num">名額</th><th className="num">倍數</th><th className="num">滿額時間(秒)</th></tr></thead>
        <tbody>{r.top_oversubscribed.slice(0, 12).map((c) => <tr key={c.id}><td>{c.name}</td><td>{c.teachers}</td><td className="num">{c.demand}</td><td className="num">{c.capacity}</td><td className="num">{c.oversub.toFixed(2)}</td><td className="num">{c.full_at == null ? "—" : c.full_at.toFixed(1)}</td></tr>)}</tbody></table></div>
    </>
  );
}

export default function Sim() {
  const [rep, setRep] = useState<Report | null>(null);
  const [custom, setCustom] = useState<Result | null>(null);
  const [p, setP] = useState({ seeds: 3, servers: 8, service_time: 0.05, capacity_factor: 1, median_arrival: 20, timeout: 30 });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { get<Report>("/api/sim/report").then(setRep).catch((e) => setErr(String(e))); }, []);
  const runSim = async () => { setBusy(true); setErr(""); try { setCustom(await post<Result>("/api/sim/run", p)); } catch (e) { setErr(String(e)); } finally { setBusy(false); } };
  const num = (k: keyof typeof p, label: string, step = 1) => (
    <label className="muted">{label} <input type="number" step={step} value={p[k]} onChange={(e) => setP({ ...p, [k]: +e.target.value })} style={{ width: 72 }} /></label>
  );
  const sens = rep?.sensitivity;
  const caps = [0.8, 1.0, 1.2], colors = ["var(--series-1)", "var(--series-2)", "var(--series-3)"];
  const v = rep?.validation;
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card">
        <h2>先搶先贏（FCFS）代理人模擬：115-1 基準結果</h2>
        <p className="note">每位代理人＝一位大學部學生（依真實班級規模產生），以隨機效用模型排出志願清單；
          開放選課後依到達時間送出請求，伺服器有限吞吐並排隊，滿額即轉下一志願。課程吸引力 α 以 115-1 實際選課人數校準（滿額課視為設限資料）。</p>
        {err && <p className="err">{err}</p>}
        {rep ? <View r={rep.main} /> : <p className="muted">載入中…</p>}
      </section>
      {sens && (
        <section className="card">
          <h2>敏感度分析：伺服器吞吐量 × 名額係數</h2>
          <div className="grid2">
            <div><h3>「手速」決定結果的程度（到達時間 vs 效用的 Spearman ρ，越負越不公平）</h3>
              <LineChart logX xLabel="伺服器吞吐（req/s，對數軸）" yLabel="ρ" yFmt={(v) => v.toFixed(2)}
                series={caps.map((c, i) => ({ name: `名額 ×${c}`, color: colors[i], points: sens.filter((s) => s.capacity_factor === c).map((s) => ({ x: s.throughput_rps, y: s.arrival_spearman })) }))} /></div>
            <div><h3>拿到第一志願比例</h3>
              <LineChart logX xLabel="伺服器吞吐（req/s，對數軸）" yLabel="比例" yFmt={pct}
                series={caps.map((c, i) => ({ name: `名額 ×${c}`, color: colors[i], points: sens.filter((s) => s.capacity_factor === c).map((s) => ({ x: s.throughput_rps, y: s.top1 })) }))} /></div>
          </div>
          <p className="muted">解讀：吞吐越低，大量請求逾時重送，結果被「隨機化」，反而削弱了先到者優勢（ρ 趨近 0），代價是大量逾時與等候；
            吞吐足夠時，到達順序成為主要決定因素。增加名額同時提升效率與公平。</p>
          <div className="scroll"><table><thead><tr><th className="num">吞吐</th><th className="num">名額×</th><th className="num">效用達成</th><th className="num">Gini</th><th className="num">ρ</th><th className="num">第一志願</th><th className="num">等候p95(s)</th><th className="num">逾時</th></tr></thead>
            <tbody>{sens.map((s, i) => <tr key={i}><td className="num">{s.throughput_rps}</td><td className="num">{s.capacity_factor}</td><td className="num">{pct(s.welfare)}</td><td className="num">{s.gini.toFixed(4)}</td><td className="num">{s.arrival_spearman.toFixed(3)}</td><td className="num">{pct(s.top1)}</td><td className="num">{s.wait_p95}</td><td className="num">{s.timeouts}</td></tr>)}</tbody></table></div>
        </section>
      )}
      {v && (
        <section className="card">
          <h2>模型驗證（hold-out）：{v.train.join("-")} 校準 → 預測 {v.test.join("-")}</h2>
          <table><thead><tr><th>模型</th><th>範圍</th><th className="num">MAE（人）</th><th className="num">Spearman ρ</th></tr></thead>
            <tbody>
              <tr><td>代理人模擬</td><td>全部 {v.n_courses} 門</td><td className="num">{v.sim_all.MAE}</td><td className="num">{v.sim_all.spearman}</td></tr>
              <tr><td>代理人模擬</td><td>前學期開過的 {v.n_seen_before} 門</td><td className="num">{v.sim_seen.MAE}</td><td className="num">{v.sim_seen.spearman}</td></tr>
              <tr><td>基準：沿用上學期人數</td><td>前學期開過的 {v.n_seen_before} 門</td><td className="num">{v.baseline_seen.MAE}</td><td className="num">{v.baseline_seen.spearman}</td></tr>
            </tbody></table>
          <p className="muted">誠實結論：在「預測人數」上，模擬僅與天真基準持平。它的價值在於回答反事實問題（換機制、改名額、改時段會怎樣），而非精準預測。</p>
        </section>
      )}
      <section className="card">
        <h2>自訂情境</h2>
        <div className="row">{num("seeds", "seeds")}{num("servers", "worker 數")}{num("service_time", "每請求秒數", 0.01)}{num("capacity_factor", "名額×", 0.1)}{num("median_arrival", "到達中位數(秒)")}{num("timeout", "逾時(秒)")}
          <button className="btn primary" onClick={runSim} disabled={busy}>{busy ? "模擬中…" : "執行"}</button></div>
        {custom && <View r={custom} />}
      </section>
    </div>
  );
}
