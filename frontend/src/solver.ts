/**
 * 瀏覽器端排課求解：分支定界（branch & bound）找分數最高的前 k 組相異課表。
 * 與後端 CP-SAT 版（backend/recommend/solver.py）同一個模型：
 *   最大化 Σ score；限制：不衝堂、同名課至多一門（必選課豁免，且其課名不得再加選）、學分介於 [min,max]、必選課一定排入。
 * 上界：目前分數 + 剩餘正分課程依「分數/學分」排序的分數背包鬆弛（fractional knapsack），保證可剪枝而不漏解。
 */
import { DAYS7, PERIODS, loadExcess, type Balance } from "./load.ts";

export type Cand = { id: string; name: string; credit: number; slots: string[]; score: number; group?: string };
export type Sol = { ids: string[]; credits: number; score: number; preference: number; penalty: number; optimal: boolean;
  load: ReturnType<typeof loadExcess> };

/** balance：分散每日負擔（扣分）。扣分隨選課只增不減（單調），因此「分數 − 目前扣分 + 剩餘上界」仍是有效上界。 */
export function solve(cands: Cand[], must: string[], minC: number, maxC: number, k = 3, nodeLimit = 3_000_000,
                      balance?: Balance): Sol[] {
  const C = (x: number) => Math.round(x * 10);
  const slotId = new Map<string, number>();
  const sid = (s: string) => { if (!slotId.has(s)) slotId.set(s, slotId.size); return slotId.get(s)!; };
  const items = cands.map((c) => ({ ...c, cr: C(c.credit), sl: c.slots.map(sid) }));
  const occ = new Uint8Array(200);
  const names = new Set<string>();
  const groups = new Set<string>();          // 每組至多一門（與後端 groups 參數一致）
  let credit = 0, base = 0;
  const chosen: string[] = [];
  const mustSet = new Set(must);
  for (const it of items.filter((i) => mustSet.has(i.id))) {
    if (it.sl.some((s) => occ[s])) return [];      // 必選課互相衝堂 → 無解（同名必選課豁免，與後端一致）
    it.sl.forEach((s) => (occ[s] = 1)); names.add(it.name); if (it.group) groups.add(it.group);
    credit += it.cr; base += it.score; chosen.push(it.id);
  }
  if (credit > C(maxC)) return [];
  const rest = items.filter((i) => !mustSet.has(i.id))
    .sort((a, b) => (b.score / Math.max(b.cr, 1)) - (a.score / Math.max(a.cr, 1)));
  const n = rest.length;
  // 每日負擔扣分（直接由已佔用節次計算；與 load.ts / 後端定義相同）
  const grid = DAYS7.map((d) => PERIODS.map((p) => slotId.get(`${d}-${p}`) ?? -1));
  const penalty = () => {
    if (!balance) return 0;
    let ex = 0;
    for (const row of grid) {
      let n = 0;
      for (let i = 0; i < row.length; i++) {
        if (row[i] >= 0 && occ[row[i]]) n++;
        if (i + balance.maxConsec < row.length) {
          let all = true;
          for (let j = i; j <= i + balance.maxConsec; j++) if (row[j] < 0 || !occ[row[j]]) { all = false; break; }
          if (all) ex++;
        }
      }
      ex += Math.max(0, n - balance.maxDaily);
    }
    return balance.weight * ex;
  };
  const best: { ids: string[]; score: number; credit: number; pref: number; pen: number }[] = [];
  const kth = () => (best.length < k ? -Infinity : best[best.length - 1].score);
  let nodes = 0, exhausted = true;

  const bound = (i: number, cap: number) => {        // 分數背包鬆弛
    let b = 0;
    for (let j = i; j < n && cap > 0; j++) {
      const it = rest[j];
      if (it.score <= 0) break;                         // 已依密度排序，之後都 ≤ 0
      if (it.cr <= cap) { b += it.score; cap -= it.cr; } else { b += it.score * (cap / it.cr); cap = 0; }
    }
    return b;
  };
  const record = (pref: number) => {
    if (credit < C(minC) || credit > C(maxC)) return;
    const pen = penalty();
    best.push({ ids: [...chosen], score: pref - pen, credit, pref, pen });
    best.sort((a, b) => b.score - a.score);
    if (best.length > k) best.pop();
  };
  const dfs = (i: number, score: number) => {
    if (++nodes > nodeLimit) { exhausted = false; return; }
    if (score - penalty() + bound(i, C(maxC) - credit) <= kth() + 1e-9) return;
    if (i === n) { record(score); return; }
    const it = rest[i];
    if (credit + it.cr <= C(maxC) && !names.has(it.name) && !(it.group && groups.has(it.group)) && !it.sl.some((s) => occ[s])) {
      it.sl.forEach((s) => (occ[s] = 1)); names.add(it.name); if (it.group) groups.add(it.group);
      credit += it.cr; chosen.push(it.id);
      dfs(i + 1, score + it.score);
      chosen.pop(); credit -= it.cr; names.delete(it.name); if (it.group) groups.delete(it.group);
      it.sl.forEach((s) => (occ[s] = 0));
    }
    dfs(i + 1, score);
  };
  dfs(0, base);
  const bySlots = (ids: string[]) => new Set(ids.flatMap((id) => cands.find((c) => c.id === id)!.slots));
  return best.map((b) => ({ ids: b.ids, credits: b.credit / 10, score: b.score, preference: b.pref, penalty: b.pen,
    optimal: exhausted, load: loadExcess(bySlots(b.ids), balance ?? { maxConsec: 3, maxDaily: 6, weight: 0 }) }));
}
