/**
 * 先修關係（純計算，可用 node 測試）。
 *
 * 課綱中的「先修課程」欄位只有 3.6% 的課有寫，且多為「負責教授同意」，能對應到課程標準的關係幾乎為零，
 * 因此改用資料中「確定存在」的結構，再讓系所補充：
 *  1. 系列課：同名但編號遞增，(一)→(二)→(三)、I→II、(1)→(2)。
 *  2. 上下學期同名必修：例如微積分（大一上）→ 微積分（大一下）。
 *  3. 系所補充檔 data/prereq.json：{ "資工系": [["計算機程式設計(二)", "資料結構"]], "*": [...] }，
 *     「*」套用到所有系所。課名以 norm() 比對。
 */
import { norm } from "./rules.ts";

export type Node = { key: string; name: string; year: number; sem: number; type: string; credit: number };
export type Edge = { from: string; to: string; kind: "series" | "same" | "manual" };
export type Supplement = Record<string, [string, string][]>;

const NUM: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, I: 1, II: 2, III: 3, IV: 4, "1": 1, "2": 2, "3": 3, "4": 4 };

/** 「電子學(一)」→ ["電子學", 1]；「科技日文II」→ ["科技日文", 2] */
export function series(name: string): [string, number] | null {
  const n = norm(name);
  let m = n.match(/^(.*?)\((一|二|三|四|I{1,3}|IV|[1-4])\)$/);
  if (m && m[1]) return [m[1], NUM[m[2]]];
  m = n.match(/^(.*?[^IV])(I{1,3}|IV)$/);
  if (m && m[1]) return [m[1], NUM[m[2]]];
  return null;
}

export function buildGraph(courses: { year: string; sem: string; type: string; name: string; credit: string }[],
                           supplement: Supplement = {}, deptKey = ""): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = courses.map((c, i) => ({ key: `${c.year}-${c.sem}-${i}`, name: c.name, year: +c.year, sem: +c.sem,
    type: c.type, credit: parseFloat(c.credit) || 0 }));
  const order = (n: Node) => n.year * 2 + n.sem;
  const edges: Edge[] = [];
  const seen = new Set<string>();
  const add = (from: Node, to: Node, kind: Edge["kind"]) => {
    const k = `${from.key}>${to.key}`;
    if (from.key === to.key || seen.has(k) || order(from) > order(to)) return;
    seen.add(k); edges.push({ from: from.key, to: to.key, kind });
  };
  // 1. 系列課
  const bySeries = new Map<string, Map<number, Node[]>>();
  for (const n of nodes) {
    const s = series(n.name);
    if (!s) continue;
    if (!bySeries.has(s[0])) bySeries.set(s[0], new Map());
    const m = bySeries.get(s[0])!;
    m.set(s[1], [...(m.get(s[1]) ?? []), n]);
  }
  for (const m of bySeries.values())
    for (const [i, as] of m) for (const b of m.get(i + 1) ?? []) for (const a of as) add(a, b, "series");
  // 2. 上下學期同名必修（體育、向度佔位課除外）
  const req = ["○", "△", "●", "▲"];
  const byName = new Map<string, Node[]>();
  for (const n of nodes) {
    if (!req.includes(n.type) || /^體育|向度/.test(n.name)) continue;
    const k = norm(n.name);
    byName.set(k, [...(byName.get(k) ?? []), n]);
  }
  for (const list of byName.values()) {
    const s = [...list].sort((a, b) => order(a) - order(b));
    for (let i = 0; i + 1 < s.length; i++) if (order(s[i]) < order(s[i + 1])) add(s[i], s[i + 1], "same");
  }
  // 3. 系所補充
  const pairs = [...(supplement["*"] ?? []), ...(supplement[deptKey] ?? [])];
  for (const [a, b] of pairs) {
    const as = nodes.filter((n) => norm(n.name) === norm(a)), bs = nodes.filter((n) => norm(n.name) === norm(b));
    for (const x of as) for (const y of bs) add(x, y, "manual");
  }
  return { nodes, edges };
}

/** 被當的課往下游影響到的課（不含自己） */
export function downstream(edges: Edge[], failed: Set<string>): Set<string> {
  const out = new Set<string>();
  const next = new Map<string, string[]>();
  for (const e of edges) next.set(e.from, [...(next.get(e.from) ?? []), e.to]);
  const stack = [...failed];
  while (stack.length) {
    for (const t of next.get(stack.pop()!) ?? []) if (!out.has(t) && !failed.has(t)) { out.add(t); stack.push(t); }
  }
  return out;
}
