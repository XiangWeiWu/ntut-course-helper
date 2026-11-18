import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildGraph, downstream, series } from "../src/prereq.ts";

const std = (y: number, k: string) => JSON.parse(readFileSync(new URL(`../public/data/standards_${y}.json`, import.meta.url), "utf8")).standards[k];
const nameOf = (g: ReturnType<typeof buildGraph>, key: string) => g.nodes.find((n) => n.key === key)!.name;

test("系列課名辨識", () => {
  assert.deepEqual(series("電子學(一)"), ["電子學", 1]);
  assert.deepEqual(series("工程數學（二）"), ["工程數學", 2]);
  assert.deepEqual(series("科技日文II"), ["科技日文", 2]);
  assert.deepEqual(series("無機化學(I)"), ["無機化學", 1]);
  assert.equal(series("微積分"), null);
});

test("電機系：電子學(一)→(二)、微積分及演練 上→下；邊一定從前面學期指向後面學期", () => {
  const g = buildGraph(std(115, "電機系").courses);
  const has = (a: string, b: string) => g.edges.some((e) => nameOf(g, e.from) === a && nameOf(g, e.to) === b);
  assert.ok(has("電子學(一)", "電子學(二)"));
  assert.ok(has("微積分及演練", "微積分及演練"));
  const ord = (k: string) => { const n = g.nodes.find((x) => x.key === k)!; return n.year * 2 + n.sem; };
  for (const e of g.edges) assert.ok(ord(e.from) <= ord(e.to));
});

test("系所補充檔與下游影響", () => {
  const g = buildGraph(std(115, "資工系").courses, { "資工系": [["計算機程式設計(二)", "資料結構"]] }, "資工系");
  const prog1 = g.nodes.find((n) => n.name === "計算機程式設計(一)")!.key;
  const hit = [...downstream(g.edges, new Set([prog1]))].map((k) => nameOf(g, k));
  assert.ok(hit.includes("計算機程式設計(二)"));   // 系列課
  assert.ok(hit.includes("資料結構"));             // 經由補充檔，兩層下游
});
