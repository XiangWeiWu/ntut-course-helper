import { useEffect, useMemo, useState } from "react";
import { get, post, slotKeys, timeText, type Course } from "../api";
import { MAX_CREDITS, REQUIRED, estimateElectives, minCredits, plan, requiredItems, type Std } from "../grad";
import { norm, parseRules } from "../rules";
import { buildGraph, downstream, type Supplement } from "../prereq";
import CourseMap, { type MapStatus } from "../components/CourseMap";
import PrereqTree from "../components/PrereqTree";
import CrowdRisk, { useCrowd } from "../components/CrowdRisk";
import Timetable from "../components/Timetable";
import LoadSummary from "../components/LoadSummary";
import { loadExcess } from "../load";

const CUR_YEAR = 115, CUR_SEM = 1;
const COHORTS = [115, 114, 113, 112];
type StdResp = { cohort: number; deptMap: Record<string, string>; standards: Record<string, Std & { rules?: string[] }> };
type Cls = { name: string; dept: string; grade: number; required: string[] };
type Sol = { courses: Course[]; credits: number; score: number; optimal: boolean };
type Saved = { cohort: number; key: string; homeClass: string; failed: string[]; pro: number | null; free: number | null; overload: number;
  electives: string[]; checks: string[] };

const LS = "ntut-grad-plan";
const loadSaved = (): Partial<Saved> => { try { return JSON.parse(localStorage.getItem(LS) || "{}"); } catch { return {}; } };

export default function Graduation() {
  const saved = useMemo(loadSaved, []);
  const [cohort, setCohort] = useState(saved.cohort ?? 113);
  const [data, setData] = useState<StdResp | null>(null);
  const [key, setKey] = useState(saved.key ?? "資工系");
  const [classes, setClasses] = useState<Cls[]>([]);
  const [homeClass, setHomeClass] = useState(saved.homeClass ?? "");
  const [failed, setFailed] = useState<Set<string>>(new Set(saved.failed ?? []));
  const [pro, setPro] = useState<number | null>(saved.pro ?? null);
  const [free, setFree] = useState<number | null>(saved.free ?? null);
  const [overload, setOverload] = useState(saved.overload ?? 0);   // 可超修的學分（0＝不超修）
  const [electivesDone, setElectivesDone] = useState<Set<string>>(new Set(saved.electives ?? []));   // 地圖上勾選已修的選修（課程 key）
  const [checks, setChecks] = useState<Set<string>>(new Set(saved.checks ?? []));                 // 人工確認的畢業門檻
  const [supplement, setSupplement] = useState<Supplement>({});
  const maxPerSem = MAX_CREDITS + overload;
  const [courses, setCourses] = useState<Course[]>([]);
  const [sols, setSols] = useState<Sol[] | null>(null);
  const [pick, setPick] = useState(0);              // 目前顯示第幾個方案
  const [balanceSet, setBalanceSet] = useState<boolean | null>(null);   // null＝依預設（有重修就開啟）
  const [maxConsec, setMaxConsec] = useState(3);
  const [maxDaily, setMaxDaily] = useState(6);
  const [crowdAlpha, setCrowdAlpha] = useState(0.5);     // 考慮其他同學（0＝不考慮）
  const crowd = useCrowd();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    get<Cls[]>("/api/classes").then(setClasses).catch(() => {});
    get<Course[]>("/api/courses?limit=10000").then(setCourses).catch(() => {});
    get<Supplement>("/api/grad/prereq").then(setSupplement).catch(() => {});
  }, []);
  useEffect(() => { setData(null); get<StdResp>(`/api/grad/standards?cohort=${cohort}`).then(setData).catch((e) => setErr(String(e))); }, [cohort]);
  useEffect(() => {
    try { localStorage.setItem(LS, JSON.stringify({ cohort, key, homeClass, failed: [...failed], pro, free, overload,
      electives: [...electivesDone], checks: [...checks] })); } catch { /* 私密瀏覽 */ }
  }, [cohort, key, homeClass, failed, pro, free, overload, electivesDone, checks]);
  const resetFor = () => { setFailed(new Set()); setPro(null); setFree(null); setSols(null); setElectivesDone(new Set()); setChecks(new Set()); };

  const std = data?.standards[key];
  const grade = CUR_YEAR - cohort + 1;
  const est = std ? estimateElectives(std, grade, CUR_SEM) : { pro: 0, free: 0 };
  const graph = useMemo(() => std ? buildGraph(std.courses, supplement, key) : { nodes: [], edges: [] }, [std, supplement, key]);
  // 地圖上勾選的選修：★ 算專業選修，其他（☆ 等）算跨域及自由選修
  const ticked = graph.nodes.filter((n) => electivesDone.has(n.key));
  const tickedPro = ticked.filter((n) => n.type === "★").reduce((a, n) => a + n.credit, 0);
  const tickedFree = ticked.filter((n) => n.type !== "★").reduce((a, n) => a + n.credit, 0);
  // pro/free 現在代表「地圖上沒有列出的其他已修學分」（他系課、通識超出等）；null＝尚未填（新生為 0，其餘依進度估計扣掉已勾選）
  const proExtra = pro ?? (electivesDone.size ? 0 : est.pro), freeExtra = free ?? (electivesDone.size ? 0 : est.free);
  const proV = tickedPro + proExtra, freeV = tickedFree + freeExtra;
  const p = useMemo(() => std ? plan(std, { cohort, currentYear: CUR_YEAR, currentSem: CUR_SEM, failed, proEarned: proV, freeEarned: freeV, overload }) : null,
    [std, cohort, failed, proV, freeV, overload]);

  // 班級：同年級；系所全名與標準相符者排前面
  const matches = (d: string) => { const full = data?.deptMap[d]; return !!full && key.startsWith(full); };
  const gradeClasses = classes.filter((c) => c.grade === grade)
    .sort((a, b) => Number(matches(b.dept)) - Number(matches(a.dept)) || a.name.localeCompare(b.name));
  useEffect(() => {   // 換標準或年級時，預設選第一個相符的班（使用者已選相符的班則保留）
    const cur = gradeClasses.find((c) => c.name === homeClass);
    if (gradeClasses.length && (!cur || (!matches(cur.dept) && matches(gradeClasses[0].dept)))) setHomeClass(gradeClasses[0].name);
  }, [gradeClasses.map((c) => c.name).join(), key, data]);   // eslint-disable-line

  const cur = p?.semesters[0];
  const failedKeys = useMemo(() => new Set([...failed].filter((k) => (p?.past ?? []).some((c) => c.key === k))), [failed, p]);
  const affected = useMemo(() => downstream(graph.edges, failedKeys), [graph, failedKeys]);
  const statusOf = (k: string): MapStatus => {
    const n = graph.nodes.find((x) => x.key === k);
    if (!n) return "future";
    const isReq = REQUIRED.includes(n.type);
    const past = n.year < grade || (n.year === grade && n.sem < CUR_SEM);
    if (!isReq) return electivesDone.has(k) ? "passed" : affected.has(k) ? "affected" : "future";
    if (past) return failed.has(k) ? "failed" : "passed";
    if (affected.has(k)) return "affected";
    return n.year === grade && n.sem === CUR_SEM ? "current" : "future";
  };
  const rules = useMemo(() => std ? parseRules(std.rules, std.courses) : null, [std]);
  const balance = balanceSet ?? (cur?.retakes.length ?? 0) > 0;
  const reqIds = new Set(classes.find((c) => c.name === homeClass)?.required ?? []);
  const reqSlots = new Set(courses.filter((c) => reqIds.has(c.id)).flatMap(slotKeys));
  /** 重修可選的班：一般課＝全校同名課；「學院指定向度-X」與「學生自選向度」是佔位課（備註「請選：通識中心/博雅課程」），
   *  實際就是選修通識課程：改選對應向度的博雅課（向度寫在博雅課備註，如「自然與科學向度」）；學生自選向度＝任一門通識。 */
  const isPlaceholder = (name: string) => name.startsWith("學院指定向度-") || name === "學生自選向度";
  const sectionsOf = (name: string) => {
    const open = (c: Course) => Object.values(c.time).some((v) => v.length) && c.people > 0;
    if (name.startsWith("學院指定向度-")) {
      const dim = name.slice("學院指定向度-".length);
      return courses.filter((c) => open(c) && c.classes.some((n) => n.startsWith("博雅課程")) && c.notes.includes(`${dim}向度`));
    }
    if (name === "學生自選向度") return courses.filter((c) => open(c) && c.classes.some((n) => n.startsWith("博雅課程")));
    return courses.filter((c) => open(c) && c.name === name);
  };

  const toggle = (k: string) => { const s = new Set(failed); s.has(k) ? s.delete(k) : s.add(k); setFailed(s); };
  const toggleElective = (k: string) => { const s = new Set(electivesDone); s.has(k) ? s.delete(k) : s.add(k); setElectivesDone(s); };
  const toggleCheck = (id: string) => { const s = new Set(checks); s.has(id) ? s.delete(id) : s.add(id); setChecks(s); };
  // 通識：由課程標準的向度佔位課計算（已通過／規劃中），與規則要求比對
  const items = std ? requiredItems(std) : [];
  const isPast = (c: { year: string; sem: string }) => +c.year < grade || (+c.year === grade && +c.sem < CUR_SEM);
  const genEdRows = rules?.genEd ? [...rules.genEd.dims.map((d) => ({ label: d, need: rules.genEd!.perDim, match: (n: string) => n === `學院指定向度-${d}` })),
    { label: "不分向度（學生自選）", need: rules.genEd.free, match: (n: string) => n === "學生自選向度" }].map((r) => {
      const its = items.filter((c) => r.match(c.name));
      return { ...r, done: its.filter((c) => isPast(c) && !failed.has(c.key)).reduce((a, c) => a + c.credits, 0),
               planned: its.filter((c) => !isPast(c) || failed.has(c.key)).reduce((a, c) => a + c.credits, 0) };
    }) : [];
  const tickedNames = new Set(ticked.map((n) => norm(n.name)));

  const schedule = async () => {
    if (!cur) return;
    setBusy(true); setErr(""); setSols(null);
    try {
      const favorites: Record<string, number> = {};
      const groups: string[][] = [];
      for (const r of cur.retakes) {                 // 每門重修：候選班一組，最多選一班，分數高＝優先
        const ids = sectionsOf(r.name).map((c) => c.id);
        ids.forEach((id) => (favorites[id] = 10));
        if (ids.length) groups.push(ids);
      }
      const minC = Math.min(Math.max(cur.requiredCredits, minCredits(cur.grade)), maxPerSem);   // 學則下限
      setPick(0);
      setSols(await post<Sol[]>("/api/schedule/solve", { home_class: homeClass || null, favorites, groups, min_credit: minC, max_credit: maxPerSem, k: 3,
        balance, max_consec: maxConsec, max_daily: maxDaily, crowd_alpha: crowdAlpha || null }));
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  };
  const missingRetakes = (s: Sol) => (cur?.retakes ?? []).filter((r) => {
    const ids = new Set(sectionsOf(r.name).map((c) => c.id));
    return !s.courses.some((c) => ids.has(c.id));
  }).map((r) => r.name);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card">
        <h2>學生畢業規劃：被當了還能準時畢業嗎？</h2>
        <p className="note">選擇入學年與課程標準後，在<b>課程地圖</b>上標出被當的必修、勾選已修的選修。系統依「該屆」課程標準與畢業規定，
          檢查通識向度、指定課群與各類學分，把重修排進剩餘學期（與原本相同的上／下學期），並判斷能否準時畢業。資料只存在你的瀏覽器。</p>
        <div className="row">
          <label className="muted">入學年 <select value={cohort} onChange={(e) => { setCohort(+e.target.value); resetFor(); }}>
            {COHORTS.map((y) => <option key={y} value={y}>{y} 學年（本學期大{"一二三四"[CUR_YEAR - y]}）</option>)}</select></label>
          <label className="muted">課程標準 <select value={key} onChange={(e) => { setKey(e.target.value); resetFor(); }}>
            {Object.keys(data?.standards ?? { [key]: 0 }).filter((k) => !k.startsWith("通識中心")).map((k) => <option key={k} value={k}>{k}</option>)}</select></label>
          <label className="muted">班級 <select value={homeClass} onChange={(e) => setHomeClass(e.target.value)}>
            {gradeClasses.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select></label>
          <span className="muted">每學期 {minCredits(grade)}–{MAX_CREDITS} 學分（學則第 15 條；大四下限 9）</span>
          <label className="muted">可超修 <input type="number" min={0} max={6} value={overload} onChange={(e) => setOverload(Math.max(0, +e.target.value))} style={{ width: 48 }} /> 學分</label>
        </div>
        {err && <p className="err">{err}</p>}
        {!std && !err && <p className="muted">載入課程標準中…</p>}
      </section>

      {p && std && <section className="card">
        <h2>1. 課程地圖（{key}，{cohort} 學年入學）</h2>
        <p className="muted">點<b>以前學期</b>的必修可切換「已通過／被當」；選修預設收合，點開勾選已修的課，專業選修學分會自動計算。
          被當的課會把下游課程標成「受先修影響」。</p>
        <CourseMap nodes={graph.nodes} statusOf={statusOf} onToggleRequired={toggle} electivesDone={electivesDone} onToggleElective={toggleElective} />
        <h3>先修關係樹狀圖</h3>
        <PrereqTree nodes={graph.nodes} edges={graph.edges} statusOf={statusOf} />
      </section>}

      {p && std && <div className="grid2">
        <section className="card">
          <h2>2. 畢業門檻檢查</h2>
          {rules?.genEd && <>
            <h3>通識（博雅）課程：應修 {rules.genEd.total} 學分</h3>
            <table><thead><tr><th>向度</th><th className="num">要求</th><th className="num">已修</th><th className="num">規劃中</th><th>狀態</th></tr></thead>
              <tbody>{genEdRows.map((r) => <tr key={r.label}><td>{r.label}</td><td className="num">{r.need}</td><td className="num">{r.done}</td><td className="num">{r.planned}</td>
                <td>{r.done >= r.need ? <span className="status"><i style={{ background: "var(--good)" }} />完成</span>
                  : r.done + r.planned >= r.need ? <span className="status"><i style={{ background: "var(--accent)" }} />已排入規劃</span>
                  : <span className="status"><i style={{ background: "var(--critical)" }} />不足</span>}</td></tr>)}</tbody></table>
            <p className="muted">課程標準中的「學院指定向度-X」「學生自選向度」就是通識課：重修或補修時改選對應向度的博雅課程。
              {rules.genEd.freeCap ? `另外，跨域及自由選修中通識博雅課程至多認列 ${rules.genEd.freeCap} 學分。` : ""}</p>
          </>}
          {rules && rules.groups.length > 0 && <>
            <h3>系上指定課群（在地圖上勾選已修的選修後自動判斷）</h3>
            {rules.groups.map((g, i) => {
              const got = g.names.filter((n) => tickedNames.has(n));
              return <div key={i} style={{ marginBottom: 8 }}>
                <span className="status"><i style={{ background: got.length >= g.k ? "var(--good)" : "var(--critical)" }} />
                  <b>{g.names.length}{g.declared ? `（規定 ${g.declared}）` : ""} 門至少 {g.k} 門</b>：已修 {got.length} 門</span>
                <div className="muted" style={{ fontSize: 12 }}>{g.names.join("、")}</div>
                {g.declared && <div className="err" style={{ fontSize: 12 }}>規則寫 {g.declared} 門，課程標準中只找到 {g.names.length} 門課名，請以系上公告為準。</div>}
              </div>;
            })}
          </>}
          {rules && rules.manual.length > 0 && <>
            <h3>需自行確認的項目</h3>
            {rules.manual.map((m) => <label key={m.id} style={{ display: "flex", gap: 6, alignItems: "flex-start", fontSize: 13, padding: "2px 0" }}>
              <input type="checkbox" checked={checks.has(m.text)} onChange={() => toggleCheck(m.text)} /><span>{m.text}</span></label>)}
          </>}
          <h3>地圖上沒列出的其他已修學分</h3>
          <div className="row">
            <label className="muted">專業選修 <input type="number" min={0} value={proExtra} onChange={(e) => setPro(Math.max(0, +e.target.value))} style={{ width: 60 }} /></label>
            <label className="muted">跨域及自由選修 <input type="number" min={0} value={freeExtra} onChange={(e) => setFree(Math.max(0, +e.target.value))} style={{ width: 60 }} /></label>
          </div>
          <p className="muted">例如他系的課、超出向度要求的通識。目前合計：專業選修 {proV}（地圖勾選 {tickedPro}）、跨域及自由選修 {freeV}（地圖勾選 {tickedFree}）。
            {pro === null && free === null && !electivesDone.size ? "尚未勾選，暫以正常進度估計。" : ""}</p>
        </section>

        <section className="card">
          <h2>3. 畢業評估</h2>
          <p className="status" style={{ fontSize: 15 }}><i style={{ background: p.onTime ? "var(--good)" : "var(--critical)", width: 12, height: 12 }} />
            <b>{p.onTime ? "依此規劃可以準時畢業" : "有延畢風險"}</b></p>
          {p.warnings.map((w, i) => <p key={i} className="err" style={{ margin: "4px 0" }}>⚠ {w}</p>)}
          <table><thead><tr><th>類別</th><th className="num">要求</th><th className="num">已修</th><th className="num">還差</th></tr></thead>
            <tbody>{p.categories.map((c) => <tr key={c.name}><td>{c.name}</td><td className="num">{c.need}</td><td className="num">{c.earned}</td>
              <td className="num">{c.remaining ? <b>{c.remaining}</b> : <span className="muted">0</span>}</td></tr>)}
              <tr><td><b>最低畢業學分</b></td><td className="num">{p.totalNeed}</td><td className="num">{p.totalEarned}</td><td className="num"><b>{Math.max(0, p.totalNeed - p.totalEarned)}</b></td></tr>
            </tbody></table>
          <h3>剩餘學期規劃</h3>
          <div className="scroll"><table><thead><tr><th>學期</th><th>必修</th><th>重修</th><th className="num">必修＋重修</th><th className="num">建議選修</th><th className="num">合計</th></tr></thead>
            <tbody>{p.semesters.map((s) => <tr key={s.term.label}>
              <td>{s.term.label}</td>
              <td className="muted">{s.required.map((c) => c.name).join("、") || "—"}</td>
              <td>{s.retakes.length ? s.retakes.map((c) => c.name).join("、") : <span className="muted">—</span>}</td>
              <td className="num">{s.requiredCredits}</td><td className="num">{s.electiveCredits}</td>
              <td className="num">{s.over ? <span className="err">{s.total}</span> : s.total}
                {s.overload && !s.over ? <div className="muted">需申請超修</div> : null}
                {s.topUp ? <div className="muted">含補足下限 {s.topUp}</div> : null}</td></tr>)}</tbody></table></div>
          <p className="muted">假設：被當的必修只在與課程標準相同的上／下學期開課；專業選修超出要求的學分可算入自由選修；
            選修平均分配；每學期學分依學則（上限 25、下限 16，大四 9），不足下限時自動補足。實際規定（如暑修、擋修、抵免）請以系上公告為準。</p>
        </section>
      </div>}

      {p && cur && <section className="card">
        <h2>4. 本學期（{cur.term.label}）重修開課查詢與排課</h2>
        {!cur.retakes.length ? <p className="muted">本學期沒有需要重修的課（下學期的重修會在 {CUR_YEAR}-2 學期排）。</p> : cur.retakes.map((r) => {
          const secs = sectionsOf(r.name);
          return <div key={r.key} style={{ marginBottom: 10 }}>
            <b>{r.name}</b> <span className="muted">{r.credits} 學分 · 本學期可選 {secs.length} 個班</span>
            {isPlaceholder(r.name) && <p className="muted" style={{ margin: "2px 0" }}>這是向度佔位課：實際要改選{r.name === "學生自選向度" ? "任一門" : `「${r.name.slice(7)}向度」的`}通識課程（通識中心開設的博雅課程）。</p>}
            {!secs.length && <p className="err">本學期查無可選的課程，可能改名或沒開，請洽系辦。</p>}
            <div className="scroll"><table><tbody>{secs.slice(0, 12).map((c) => {
              const clash = slotKeys(c).some((k) => reqSlots.has(k));
              return <tr key={c.id}><td>{isPlaceholder(r.name) ? <>{c.name} <span className="muted">{c.classes.join("、")}</span></> : c.classes.join("、")}</td><td>{timeText(c)}</td><td className="muted">{c.teachers.join("、")}</td>
                <td>{clash ? <span className="status"><i style={{ background: "var(--critical)" }} />與 {homeClass} 必修衝堂</span>
                  : <span className="status"><i style={{ background: "var(--good)" }} />可修</span>}</td></tr>;
            })}</tbody></table></div>
          </div>;
        })}
        <div className="row">
          <label className="muted"><input type="checkbox" checked={balance} onChange={(e) => setBalanceSet(e.target.checked)} /> 分散每日負擔</label>
          <label className="muted">連續上課 ≤ <input type="number" min={1} max={10} value={maxConsec} onChange={(e) => setMaxConsec(+e.target.value)} style={{ width: 48 }} /> 節</label>
          <label className="muted">每天 ≤ <input type="number" min={1} max={14} value={maxDaily} onChange={(e) => setMaxDaily(+e.target.value)} style={{ width: 48 }} /> 節</label>
          <span className="muted">{balanceSet === null && cur.retakes.length ? "（有重修，預設開啟）" : ""}超過時扣分、盡量避免，不會因此排不出課。</span>
          <label className="muted">考慮其他同學 <select value={crowdAlpha} onChange={(e) => setCrowdAlpha(+e.target.value)}>
            <option value={0}>不考慮</option><option value={0.25}>25% 照推薦</option><option value={0.5}>50% 照推薦</option><option value={1}>100% 照推薦</option></select></label>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>依據：連續上課沒有休息會造成認知疲勞，且對學習較弱的學生影響最大（Williams &amp; Shapiro, 2018）；休息能恢復表現、對低成就學生效果較大（Sievertsen 等, 2016, PNAS）。</p>
        <div className="row">
          <button className="btn primary" onClick={schedule} disabled={busy || !homeClass}>{busy ? "排課中…" : "排出本學期課表（重修優先）"}</button>
          <span className="muted">會放入 {homeClass} 的必修、從各班挑不衝堂的重修時段，再補選修到 {cur.min}–{maxPerSem} 學分。</span>
        </div>
        {sols && sols.length > 0 && (() => {
          const i = Math.min(pick, sols.length - 1), s = sols[i], miss = missingRetakes(s);
          const others = sols.map((o, j) => j === i ? "" : o.courses.filter((c) => !s.courses.some((x) => x.id === c.id)).map((c) => c.name).join("、"));
          return <div style={{ marginTop: 12 }}>
            <div className="row">
              {sols.map((o, j) => <button key={j} className={`btn ${j === i ? "primary" : ""}`} onClick={() => setPick(j)}>方案 {j + 1}（{o.credits} 學分）</button>)}
            </div>
            <div className="row"><span className="muted">{s.optimal ? "最佳解" : "可行解"}</span>
              {miss.length ? <span className="status"><i style={{ background: "var(--critical)" }} />排不進：{miss.join("、")}（可選的班都與必修衝堂或已滿學分上限）</span>
                : cur.retakes.length ? <span className="status"><i style={{ background: "var(--good)" }} />重修全部排入</span> : null}</div>
            <LoadSummary courses={s.courses} maxConsec={maxConsec} maxDaily={maxDaily} />
            {crowdAlpha > 0 && <CrowdRisk courses={s.courses} alpha={crowdAlpha} crowd={crowd} />}
            {(() => {
              const base = loadExcess(reqSlots, { maxConsec, maxDaily, weight: 0 });
              return base.consec_excess + base.daily_excess > 0
                ? <p className="muted" style={{ marginTop: 0 }}>其中 {homeClass} 的必修本身就造成「連續超出 {base.consec_excess} 節、每日超出 {base.daily_excess} 節」，這部分無法靠選課避免（可向系辦反映，見「系所排課最佳化」）。</p>
                : null;
            })()}
            <Timetable courses={s.courses} />
            {sols.map((o, j) => j !== i && others[j] ? <p key={j} className="muted">方案 {j + 1} 與此方案不同的課：{others[j]}</p> : null)}
          </div>;
        })()}
      </section>}
    </div>
  );
}
