/** 推薦課表的計分（與 backend/recommend/scoring.py 完全相同的規則；tests/scoring.test.mts 以全校各班交叉比對）。 */
export type SC = { id: string; credit: number; type: string; classes: string[]; required: boolean; people: number;
  dept: string | null; grades: number[]; slots: string[] };
export type Cls = { name: string; dept: string; grade: number; required: string[] };
export type Req = { home_class?: string | null; favorites?: Record<string, number>; exclude?: string[]; must?: string[];
  avoid_early?: boolean; avoid_evening?: boolean };

export function buildScores(all: SC[], classes: Cls[], r: Req, prices: Record<string, number> = {}) {
  const byId = new Map(all.map((c) => [c.id, c]));
  const must: string[] = [...(r.must ?? [])];
  let dept: string | null = null, grade: number | null = null;
  const g = r.home_class ? classes.find((x) => x.name === r.home_class) : undefined;
  if (g) {
    dept = g.dept; grade = g.grade;
    const occ = new Set<string>();
    for (const id of g.required) {                       // 預排必修（去衝堂）
      const c = byId.get(id)!;
      if (!c.slots.some((s) => occ.has(s))) { must.push(id); c.slots.forEach((s) => occ.add(s)); }
    }
  }
  const fav = r.favorites ?? {}, exclude = new Set(r.exclude ?? []);
  const scores = new Map<string, number>();
  for (const c of all) {
    let s = fav[c.id];
    if (exclude.has(c.id) || !c.slots.length || c.people === 0 || (c.credit <= 0 && s === undefined)) continue;
    if (s === undefined) {
      const boya = c.classes.some((n) => n.startsWith("博雅課程"));
      if (c.required && !boya) continue;            // 博雅課標為 △，但學生可自由選（與後端相同）
      if (dept && c.dept === dept && (!grade || c.grades.includes(grade))) s = 0.6;
      else if (c.type === "☆" || boya || (dept && c.dept === dept)) s = 0.3;
      else continue;
    }
    const periods = c.slots.map((x) => x.split("-")[1]);
    if (r.avoid_early) s -= 0.4 * periods.filter((p) => p === "1").length;
    if (r.avoid_evening ?? true) s -= 0.4 * periods.filter((p) => "ABCD".includes(p)).length;
    s -= prices[c.id] ?? 0;                                // 群體擁擠扣分
    scores.set(c.id, s * Math.max(c.credit, 1));
  }
  return { scores, must };
}
