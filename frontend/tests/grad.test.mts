// 執行：cd frontend && npm test
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { estimateElectives, plan, requiredItems, type Std } from "../src/grad.ts";

const load = (y: number, key: string): Std =>
  JSON.parse(readFileSync(new URL(`../public/data/standards_${y}.json`, import.meta.url), "utf8")).standards[key];
const base = { currentYear: 115, currentSem: 1, maxPerSem: 25 };

test("新生沒有被當：必修 92 學分全在未來、選修 40 學分、可準時畢業", () => {
  const std = load(115, "資工系");
  const p = plan(std, { ...base, cohort: 115, failed: new Set(), proEarned: 0, freeEarned: 0 });
  assert.equal(p.grade, 1);
  assert.equal(p.semesters.length, 8);
  assert.equal(p.semesters.reduce((a, s) => a + s.requiredCredits, 0), 92);
  assert.equal(p.electiveNeeded, 40);
  assert.ok(p.onTime);
});

test("必修學分守恆：已通過＋剩餘學期必修＋重修＝標準要求（各屆各系）", () => {
  for (const y of [112, 113, 114, 115]) {
    const all = JSON.parse(readFileSync(new URL(`../public/data/standards_${y}.json`, import.meta.url), "utf8")).standards;
    for (const key of ["資工系", "電機系", "建築系", "機械系"]) {
      const std: Std = all[key];
      if (!std) continue;
      const items = requiredItems(std);
      const total = items.reduce((a, c) => a + c.credits, 0);
      const failed = new Set(items.filter((_, i) => i % 5 === 0).map((c) => c.key));   // 任意一組被當
      const p = plan(std, { ...base, cohort: y, failed, proEarned: 0, freeEarned: 0 });
      const passed = p.past.filter((c) => !failed.has(c.key)).reduce((a, c) => a + c.credits, 0);
      const future = p.semesters.reduce((a, s) => a + s.requiredCredits, 0);
      const lost = p.past.filter((c) => failed.has(c.key) && !p.semesters.some((s) => s.retakes.some((r) => r.key === c.key)))
        .reduce((a, c) => a + c.credits, 0);
      assert.equal(passed + future + lost, total, `${y} ${key}`);
    }
  }
});

test("重修排在相同學期別中最早的一學期", () => {
  const std = load(113, "資工系");                     // 113 入學 → 115-1 為大三上
  const items = requiredItems(std);
  const up = items.find((c) => c.year === "2" && c.sem === "1" && c.credits > 0)!;
  const down = items.find((c) => c.year === "1" && c.sem === "2" && c.credits > 0)!;
  const p = plan(std, { ...base, cohort: 113, failed: new Set([up.key, down.key]), proEarned: 10, freeEarned: 10 });
  assert.equal(p.grade, 3);
  assert.deepEqual(p.semesters[0].retakes.map((c) => c.key), [up.key]);     // 115-1
  assert.deepEqual(p.semesters[1].retakes.map((c) => c.key), [down.key]);   // 115-2
});

test("大四上被當很多大一上的課 → 學分不足，判定可能延畢", () => {
  const std = load(112, "電機系");
  const items = requiredItems(std);
  const failed = new Set(items.filter((c) => +c.year <= 3 && c.sem === "1").map((c) => c.key));
  const p = plan(std, { ...base, cohort: 112, failed, proEarned: 0, freeEarned: 0 });
  assert.equal(p.grade, 4);
  assert.equal(p.onTime, false);
  assert.ok(p.warnings.length > 0);
});

test("專業選修超出的學分算入自由選修；估計值依進度比例", () => {
  const std = load(114, "資工系");
  const p = plan(std, { ...base, cohort: 114, failed: new Set(), proEarned: 30, freeEarned: 0 });
  const free = p.categories.find((c) => c.name.startsWith("跨域及自由選修"))!;
  assert.equal(free.earned, 30 - 20);
  const e = estimateElectives(std, 2, 1);                // 已過 2 學期 → 1/4
  assert.equal(e.pro, 5);
});
