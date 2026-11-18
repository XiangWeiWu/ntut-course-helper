import { useEffect, useMemo, useState } from "react";
import { get, post, slotKeys, timeText, type Course } from "../api";
import Timetable from "../components/Timetable";

type Cls = { name: string; dept: string; grade: number; size: number };
type Sol = { courses: Course[]; credits: number; score: number; optimal: boolean };

export default function Student() {
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [english, setEnglish] = useState(false);
  const [results, setResults] = useState<Course[]>([]);
  const [picked, setPicked] = useState<Course[]>([]);
  const [classes, setClasses] = useState<Cls[]>([]);
  const [hc, setHc] = useState("");
  const [range, setRange] = useState<[number, number]>([16, 25]);
  const [avoidEarly, setAvoidEarly] = useState(false);
  const [sols, setSols] = useState<Sol[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { get<Cls[]>("/api/classes").then(setClasses).catch((e) => setErr(String(e))); }, []);
  const search = () => {
    const p = new URLSearchParams({ q, type, limit: "120" });
    if (english) p.set("english", "true");
    get<Course[]>(`/api/courses?${p}`).then(setResults).catch((e) => setErr(String(e)));
  };
  useEffect(search, []); // eslint-disable-line

  const taken = useMemo(() => new Set(picked.flatMap(slotKeys)), [picked]);
  const conflictsWith = (c: Course) => slotKeys(c).some((k) => taken.has(k));
  const credits = picked.reduce((s, c) => s + c.credit, 0);
  const add = (c: Course) => !picked.some((p) => p.id === c.id) && setPicked([...picked, c]);
  const remove = (id: string) => setPicked(picked.filter((c) => c.id !== id));

  const solve = async () => {
    setBusy(true); setErr("");
    try {
      const favorites = Object.fromEntries(picked.map((c) => [c.id, 3]));
      setSols(await post<Sol[]>("/api/schedule/solve", { home_class: hc || null, favorites, min_credit: range[0], max_credit: range[1], avoid_early: avoidEarly }));
    } catch (e) { setErr(String(e)); setSols(null); } finally { setBusy(false); }
  };
  const nConflicts = picked.reduce((n, c, i) => n + picked.slice(i + 1).filter((d) => slotKeys(d).some((k) => slotKeys(c).includes(k))).length, 0);

  return (
    <div className="grid2">
      <section className="card">
        <h2>課程搜尋（115 學年第 1 學期）</h2>
        <div className="row">
          <input placeholder="課名 / 教師 / 課號" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} style={{ flex: 1, minWidth: 140 }} />
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">全部類別</option><option value="★">★ 專業選修</option><option value="☆">☆ 共同選修(通識)</option>
            <option value="●▲">●▲ 專業必修</option><option value="○△">○△ 共同必修</option>
          </select>
          <label className="muted"><input type="checkbox" checked={english} onChange={(e) => setEnglish(e.target.checked)} /> 英語授課</label>
          <button className="btn primary" onClick={search}>搜尋</button>
        </div>
        <div className="list">
          {results.map((c) => {
            const conf = conflictsWith(c);
            return (
              <div className="item" key={c.id}>
                <div>
                  <div className="name">{c.name} <span className="muted">{c.id}</span></div>
                  <div className="muted">
                    <span className="tag">{c.type} {c.typeName}</span>{c.credit} 學分 · {timeText(c)} · {c.teachers.join("、")}
                  </div>
                  <div className="muted">{c.classes.join("、")} · 選課 {c.people} / 估計上限 {c.capacity}
                    {c.capacitySource !== "notes" && <span title="資料無人數上限欄位，此為推估"> (推估)</span>}
                  </div>
                </div>
                <button className="btn" onClick={() => add(c)} disabled={picked.some((p) => p.id === c.id)}>
                  {conf ? "加入(衝堂)" : "加入"}
                </button>
              </div>
            );
          })}
          {!results.length && <div className="muted">沒有符合的課程</div>}
        </div>
      </section>
      <section className="card">
        <h2>我的課表</h2>
        <div className="row">
          <span className="stat"><span className="v">{credits}</span> <span className="k">學分</span></span>
          {nConflicts > 0
            ? <span className="status"><i style={{ background: "var(--critical)" }} />衝堂 {nConflicts} 處（紅色格）</span>
            : <span className="status"><i style={{ background: "var(--good)" }} />無衝堂</span>}
          <span className="muted">點課名可移除</span>
        </div>
        <Timetable courses={picked} onRemove={remove} />
        <h3>自動排課（CP-SAT 最佳化）</h3>
        <div className="row">
          <select value={hc} onChange={(e) => setHc(e.target.value)}>
            <option value="">不指定班級</option>
            {classes.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
          </select>
          <label className="muted">學分 <input type="number" value={range[0]} onChange={(e) => setRange([+e.target.value, range[1]])} style={{ width: 56 }} />–
            <input type="number" value={range[1]} onChange={(e) => setRange([range[0], +e.target.value])} style={{ width: 56 }} /></label>
          <label className="muted"><input type="checkbox" checked={avoidEarly} onChange={(e) => setAvoidEarly(e.target.checked)} /> 避開第1節</label>
          <button className="btn primary" onClick={solve} disabled={busy}>{busy ? "計算中…" : "產生 3 組課表"}</button>
        </div>
        <p className="muted">已加入的課視為「想修」，加上班級必修（預排）與同系同年級選修，在不衝堂、學分範圍內最大化偏好。夜間時段預設扣分。</p>
        {err && <p className="err">{err}</p>}
        {sols?.map((s, i) => (
          <div key={i} style={{ marginTop: 10 }}>
            <div className="row"><b>方案 {i + 1}</b><span className="muted">{s.credits} 學分 · 分數 {s.score.toFixed(1)}{s.optimal ? " · 最佳解" : ""}</span>
              <button className="btn" onClick={() => setPicked(s.courses)}>套用</button></div>
            <div className="muted">{s.courses.map((c) => c.name).join("、")}</div>
          </div>
        ))}
      </section>
    </div>
  );
}
