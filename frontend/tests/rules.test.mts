import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { findNames, norm, parseRules } from "../src/rules.ts";

const std = (y: number) => JSON.parse(readFileSync(new URL(`../public/data/standards_${y}.json`, import.meta.url), "utf8")).standards;
const parse = (y: number, key: string) => { const s = std(y)[key]; return parseRules(s.rules, s.courses); };

test("通識規則：112–115 各系（排除通識中心）全部可解析", () => {
  let n = 0;
  for (const y of [112, 113, 114, 115]) for (const [k, s] of Object.entries<any>(std(y))) {
    if (k.startsWith("通識中心") || !(s.rules ?? []).some((r: string) => r.includes("博雅課程應修滿"))) continue;
    const r = parseRules(s.rules, s.courses);
    assert.ok(r.genEd, `${y} ${k}`);
    assert.equal(r.genEd!.dims.length, 3, `${y} ${k}`);
    assert.equal(r.genEd!.dims.length * r.genEd!.perDim + r.genEd!.free, r.genEd!.total, `${y} ${k}`);
    n++;
  }
  assert.ok(n >= 150);
});

test("資工系：電資學院指定三向度、每向度 4 學分、自選 3；通識在自由選修至多認列 4 學分", () => {
  const g = parse(115, "資工系").genEd!;
  assert.deepEqual(g.dims, ["人文與藝術", "社會與法治", "創新與創業"]);
  assert.equal(g.perDim, 4); assert.equal(g.free, 3); assert.equal(g.freeCap, 4);
});

test("電機系課群：3 選 2、3 選 2、9 選 1", () => {
  const r = parse(115, "電機系");
  const g1 = r.groups.find((g) => g.names.includes(norm("電力系統(一)")))!;
  assert.deepEqual(g1.names, ["電力系統(一)", "電機機械(一)", "電力電子學"].map(norm));
  assert.equal(g1.k, 2);
  const g3 = r.groups.find((g) => g.names.includes(norm("機器學習基礎")))!;
  assert.equal(g3.k, 1);
  assert.ok(r.manual.some((m) => m.text.includes("五項所規範之其中四項")));   // 規則的規則 → 人工
});

test("化工系：一句兩個課群（「；」分隔），學期註記 (2下) 不影響比對", () => {
  const r = parse(115, "化工系");
  const a = r.groups.find((g) => g.names.includes(norm("有機化學(二)")))!;
  assert.equal(a.k, 2); assert.equal(a.names.length, 3);
  const b = r.groups.find((g) => g.names.includes(norm("環境工程")))!;
  assert.equal(b.k, 1); assert.equal(b.names.length, 4);
});

test("「下列六門課…之其中五門」取 5；長名優先不誤認短名", () => {
  for (const [k, s] of Object.entries<any>(std(115))) {
    const g = parseRules(s.rules, s.courses).groups.find((x) => x.text.includes("之其中五門"));
    if (g) { assert.equal(g.k, 5, k); return; }
  }
  assert.deepEqual(findNames("物理化學(二)、物理", ["物理", "物理化學(二)"]), ["物理化學(二)", "物理"]);
});

test("無法對應課名的符號課群（※）列為人工勾選", () => {
  const r = parse(115, "分子系");
  assert.ok(r.manual.some((m) => m.text.includes("※")));
  assert.ok(r.manual.some((m) => m.text.includes("英文畢業門檻")));
});

test("材資系：同一句用逗號接三個課群 → 3選2、2選1、3選1（不可合併）", () => {
  const r = parse(115, "材資系【材料組】");
  const g = (n: string) => r.groups.find((x) => x.names.includes(norm(n)))!;
  assert.equal(g("陶瓷材料").names.length, 3); assert.equal(g("陶瓷材料").k, 2);
  assert.equal(g("結晶學").names.length, 2); assert.equal(g("結晶學").k, 1);
  assert.equal(g("材料力學").k, 1);
});

test("分子系：課群不含必修實驗（除了必修之…外）", () => {
  const r = parse(115, "分子系");
  const g = r.groups.find((x) => x.k === 3)!;
  assert.ok(!g.names.includes(norm("基礎分子化學實驗")));
});

test("規則寫的門數多於找得到的課名時，記錄 declared 供畫面提醒", () => {
  const r = parse(115, "機電學士班【能源與冷凍空調工程系】");
  const g = r.groups[0];
  assert.equal(g.declared, 5);
  assert.equal(g.names.length, 4);
});
