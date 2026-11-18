/** 靜態模式（GitHub Pages）：以預先匯出的 JSON 在瀏覽器內回答與後端 API 相同的請求。 */
import { solve, type Cand } from "./solver";

const BASE = import.meta.env.BASE_URL;
const cache = new Map<string, Promise<any>>();
const load = (f: string) => {
  if (!cache.has(f)) cache.set(f, fetch(`${BASE}data/${f}`).then((r) => { if (!r.ok) throw new Error(`無法載入 ${f}`); return r.json(); }));
  return cache.get(f)!;
};

type C = { id: string; name: string; nameEn: string; credit: number; type: string; classes: string[]; teachers: string[];
  time: Record<string, string[]>; people: number; capacity: number; capacitySource: string; language: string;
  dept: string | null; grades: number[]; required: boolean; general: boolean; slots: string[]; code?: string };

const LS_KEY = "ntut-capacity-reports";
const myReports = (): Record<string, number> => { try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch { return {}; } };
const saveReport = (id: string, v: number) => { try { localStorage.setItem(LS_KEY, JSON.stringify({ ...myReports(), [id]: v })); } catch { /* 私密瀏覽 */ } };
const withReports = <T extends { id: string; capacity: number; capacitySource: string }>(c: T): T => {
  const r = myReports()[c.id];
  return r ? { ...c, capacity: r, capacitySource: "teacher" } : c;
};

const advice = (o: number, src: string) =>
  o < 0.4 && !["notes", "teacher"].includes(src) ? "需求/名額偏低，但名額為推估（可能高估）：請先確認實際上限"
  : o >= 1.5 ? "需求遠超名額：建議加開班或擴大教室"
  : o >= 1.0 ? "接近滿額：可考慮小幅增加名額"
  : o < 0.4 ? "需求偏低：檢視時段是否與必修衝堂" : "供需平衡";

async function courses(p: URLSearchParams) {
  const q = p.get("q") || "", type = p.get("type") || "", dept = p.get("dept") || "";
  const english = p.get("english") === "true", limit = +(p.get("limit") || 200);
  const out: C[] = [];
  for (const c of (await load("courses.json")) as C[]) {
    if (q && !c.name.includes(q) && !c.nameEn.includes(q) && !c.teachers.some((t) => t.includes(q)) && q !== c.id) continue;
    if (dept && dept !== (c.dept ?? "") && !c.classes.some((n) => n.includes(dept))) continue;
    if (type && !type.includes(c.type)) continue;
    if (english && c.language !== "英語") continue;
    out.push(withReports(c));
    if (out.length >= limit) break;
  }
  return out;
}

async function scheduleSolve(r: any) {
  const all = (await load("courses.json")) as C[];
  const byId = new Map(all.map((c) => [c.id, c]));
  const must: string[] = [...(r.must ?? [])];
  let dept: string | null = null, grade: number | null = null;
  if (r.home_class) {
    const g = ((await load("classes.json")) as any[]).find((x) => x.name === r.home_class);
    if (g) {
      dept = g.dept; grade = g.grade;
      const occ = new Set<string>();
      for (const id of g.required as string[]) {            // 預排必修（去衝堂）
        const c = byId.get(id)!;
        if (!c.slots.some((s) => occ.has(s))) { must.push(id); c.slots.forEach((s) => occ.add(s)); }
      }
    }
  }
  const fav: Record<string, number> = r.favorites ?? {};
  const scores = new Map<string, number>();
  for (const c of all) {
    let s = fav[c.id];
    if ((r.exclude ?? []).includes(c.id) || !c.slots.length || c.people === 0 || (c.credit <= 0 && s === undefined)) continue;
    if (s === undefined) {
      if (c.required) continue;
      if (dept && c.dept === dept && (!grade || c.grades.includes(grade))) s = 0.6;
      else if (c.type === "☆") s = 0.3;
      else continue;
    }
    const periods = c.slots.map((x) => x.split("-")[1]);
    if (r.avoid_early) s -= 0.4 * periods.filter((p) => p === "1").length;
    if (r.avoid_evening ?? true) s -= 0.4 * periods.filter((p) => "ABCD".includes(p)).length;
    scores.set(c.id, s * Math.max(c.credit, 1));   // 與後端一致：0 學分的收藏課仍有分數
  }
  const groupOf = new Map<string, string>();
  (r.groups ?? []).forEach((g: string[], i: number) => g.forEach((id) => groupOf.set(id, `g${i}`)));
  const cands: Cand[] = all.filter((c) => c.slots.length && (scores.has(c.id) || must.includes(c.id)))
    .map((c) => ({ id: c.id, name: c.name, credit: c.credit, slots: c.slots, score: scores.get(c.id) ?? 0, group: groupOf.get(c.id) }));
  const sols = solve(cands, must, r.min_credit ?? 16, r.max_credit ?? 25, r.k ?? 3);
  if (!sols.length) throw new Error("找不到可行課表（必修衝堂或學分範圍無法滿足）");
  return sols.map((s) => ({ ...s, courses: s.ids.map((i) => withReports(byId.get(i)!)) }));
}

async function teacherDemand(p: URLSearchParams) {
  const teacher = p.get("teacher") || "", dept = p.get("dept") || "";
  const rows = ((await load("teacher_demand.json")) as any[])
    .filter((r) => (!teacher || r.teachers.some((t: string) => t.includes(teacher))) && (teacher || !dept || r.dept === dept))
    .map((r) => { const x = withReports(r); const oversub = x.demand / Math.max(x.capacity, 1); return { ...x, oversub, advice: advice(oversub, x.capacitySource) }; });
  return rows.sort((a, b) => b.oversub - a.oversub).slice(0, 300);
}

async function deptConflicts(p: URLSearchParams) {
  const dept = p.get("dept") || "";
  const grid = new Map<string, { grade: number; day: string; period: string; required: number; electives: string[] }>();
  for (const c of (await load("courses.json")) as C[]) {
    if ((c.dept ?? "") !== dept || !c.slots.length) continue;
    for (const s of c.slots) {
      const [day, period] = s.split("-");
      for (const g of c.grades) {
        const k = `${g}|${day}|${period}`;
        if (!grid.has(k)) grid.set(k, { grade: g, day, period, required: 0, electives: [] });
        const cell = grid.get(k)!;
        if (c.required) cell.required++; else cell.electives.push(c.name);
      }
    }
  }
  return [...grid.values()];
}

/** 模擬：從預先算好的情境中挑最接近使用者選擇的參數 */
export const SCENARIO_CHOICES = { priority_days: [0, 7], p_approve: [0, 0.5, 0.9], capacity_factor: [0.8, 1.0, 1.2] };
const nearest = (v: number, xs: number[]) => xs.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));
const fmt = (x: number) => (Number.isInteger(x) ? `${x}.0` : `${x}`);
async function simRun(r: any) {
  const sc = await load("scenarios.json");
  const cap = nearest(r.capacity_factor ?? 1, SCENARIO_CHOICES.capacity_factor);
  const key = r.mechanism === "fcfs" ? `fcfs|-|-|${fmt(cap)}`
    : `ntut|${nearest(r.priority_days ?? 7, SCENARIO_CHOICES.priority_days)}|${fmt(nearest(r.p_approve ?? 0.8, SCENARIO_CHOICES.p_approve))}|${fmt(cap)}`;
  if (!sc[key]) throw new Error(`沒有預先計算的情境：${key}`);
  return sc[key];
}

export async function staticRequest(method: "GET" | "POST", url: string, body?: any): Promise<any> {
  const u = new URL(url, "http://x");
  const p = u.searchParams;
  const tt = u.pathname.match(/^\/api\/timetable\/(.+)$/);
  if (method === "GET" && tt) {
    const name = decodeURIComponent(tt[1]);
    if (name === "summary") return load("timetable/summary.json");
    const sc = p.get("scenario") === "B" ? "B" : "A";
    return load(`timetable/${encodeURIComponent(`${name}_${sc}`)}.json`);
  }
  switch (`${method} ${u.pathname}`) {
    case "GET /api/classes": return load("classes.json");
    case "GET /api/courses": return courses(p);
    case "POST /api/schedule/solve": return scheduleSolve(body);
    case "GET /api/teacher/demand": return teacherDemand(p);
    case "GET /api/dept/conflicts": return deptConflicts(p);
    case "GET /api/sim/report": return load("sim_report.json");
    case "GET /api/grad/standards": return load(`standards_${p.get("cohort")}.json`);
    case "POST /api/sim/run": return simRun(body);
    case "POST /api/capacity": {
      saveReport(body.course_id, body.capacity);
      return { id: body.course_id, capacity: body.capacity, capacitySource: "teacher" };
    }
  }
  throw new Error(`靜態版不支援：${method} ${u.pathname}`);
}
