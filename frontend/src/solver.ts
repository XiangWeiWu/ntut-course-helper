/**
 * 瀏覽器端排課求解：分支定界（branch & bound）找分數最高的前 k 組相異課表。
 * 與後端 CP-SAT 版（backend/recommend/solver.py）同一個模型：
 *   最大化 Σ score；限制：不衝堂、同名課至多一門（必選課豁免，且其課名不得再加選）、學分介於 [min,max]、必選課一定排入。
 * 上界：目前分數 + 剩餘正分課程依「分數/學分」排序的分數背包鬆弛（fractional knapsack），保證可剪枝而不漏解。
 */
export type Cand = { id: string; name: string; credit: number; slots: string[]; score: number };
export type Sol = { ids: string[]; credits: number; score: number; optimal: boolean };

export function solve(cands: Cand[], must: string[], minC: number, maxC: number, k = 3, nodeLimit = 3_000_000): Sol[] {
  const C = (x: number) => Math.round(x * 10);
  const slotId = new Map<string, number>();
  const sid = (s: string) => { if (!slotId.has(s)) slotId.set(s, slotId.size); return slotId.get(s)!; };
  const items = cands.map((c) => ({ ...c, cr: C(c.credit), sl: c.slots.map(sid) }));
  const occ = new Uint8Array(200);
  const names = new Set<string>();
  let credit = 0, base = 0;
  const chosen: string[] = [];
  const mustSet = new Set(must);
  for (const it of items.filter((i) => mustSet.has(i.id))) {
    if (it.sl.some((s) => occ[s])) return [];      // 必選課互相衝堂 → 無解（同名必選課豁免，與後端一致）
    it.sl.forEach((s) => (occ[s] = 1)); names.add(it.name); credit += it.cr; base += it.score; chosen.push(it.id);
  }
  if (credit > C(maxC)) return [];
  const rest = items.filter((i) => !mustSet.has(i.id))
    .sort((a, b) => (b.score / Math.max(b.cr, 1)) - (a.score / Math.max(a.cr, 1)));
  const n = rest.length;
  const best: { ids: string[]; score: number; credit: number }[] = [];
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
  const record = (score: number) => {
    if (credit < C(minC) || credit > C(maxC)) return;
    best.push({ ids: [...chosen], score, credit });
    best.sort((a, b) => b.score - a.score);
    if (best.length > k) best.pop();
  };
  const dfs = (i: number, score: number) => {
    if (++nodes > nodeLimit) { exhausted = false; return; }
    if (score + bound(i, C(maxC) - credit) <= kth() + 1e-9) return;
    if (i === n) { record(score); return; }
    const it = rest[i];
    if (credit + it.cr <= C(maxC) && !names.has(it.name) && !it.sl.some((s) => occ[s])) {
      it.sl.forEach((s) => (occ[s] = 1)); names.add(it.name); credit += it.cr; chosen.push(it.id);
      dfs(i + 1, score + it.score);
      chosen.pop(); credit -= it.cr; names.delete(it.name); it.sl.forEach((s) => (occ[s] = 0));
    }
    dfs(i + 1, score);
  };
  dfs(0, base);
  return best.map((b) => ({ ids: b.ids, credits: b.credit / 10, score: b.score, optimal: exhausted }));
}
