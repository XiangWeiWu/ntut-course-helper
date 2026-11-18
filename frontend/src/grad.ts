/**
 * 學生端畢業規劃（純計算，不依賴瀏覽器，可用 node 測試）。
 *
 * 依據：該屆（入學年）課程標準。已用資料查證：標準中列出的必修（○△●▲）學分加總
 * 恰等於各必修類別要求（例：資工系 115 屆 校訂共同必修 28、校訂專業必修 64），
 * 因此「必修」以逐門課程追蹤；選修（專業選修、跨域及自由選修）以學分數追蹤。
 *
 * 規則（假設，畫面上會標示）：
 * - 本學期為 115 學年第 1 學期；第 g 年級＝115−入學年+1。
 * - 被當的必修只在「與課程標準相同的學期別」（上或下學期）開課 → 排在剩餘學期中最早的同學期別。
 * - 專業選修超出要求的學分，可算入跨域及自由選修。
 * - 選修學分平均分配到剩餘學期。
 * - 每學期學分依學則第 15 條（寫死）：上限 25；下限 大一～大三 16、大四 9。
 *   可超修（使用者輸入可多修的學分，例如前 20% 可加選 1–2 門）；超過 25 的學期會標示「需申請超修」。
 *   低於下限時自動補選修到下限（這些學分可能超過畢業所需，算自由選修）。
 */
export const MAX_CREDITS = 25;
export const minCredits = (grade: number) => (grade >= 4 ? 9 : 16);
export type StdCourse = { year: string; sem: string; type: string; name: string; credit: string };
export type Std = { credits: Record<string, string>; courses: StdCourse[] };

export const REQUIRED = ["○", "△", "●", "▲"];
export const CAT: Record<string, string> = {
  "○": "部訂共同必修學分", "△": "校訂共同必修學分", "☆": "共同選修學分",
  "●": "部訂專業必修學分", "▲": "校訂專業必修學分", "★": "專業選修學分",
};
const PRO = "專業選修學分";
const FREE = "跨域及自由選修學分";
const TOTAL = "最低畢業學分數";

export type Item = StdCourse & { key: string; credits: number };
export type Term = { year: number; sem: number; label: string };
export type Inputs = { cohort: number; currentYear: number; currentSem: number; failed: Set<string>;
  proEarned: number; freeEarned: number; overload: number };
export type SemPlan = { term: Term; grade: number; required: Item[]; retakes: Item[]; requiredCredits: number;
  electiveCredits: number; total: number; min: number; max: number;
  over: boolean;        // 光必修＋重修就超過 上限＋可超修 → 不可行
  overload: boolean;    // 合計超過 25，需申請超修
  topUp: number;        // 為了達到最低學分而多補的選修學分
};
export type Plan = {
  grade: number; past: Item[]; categories: { name: string; need: number; earned: number; remaining: number }[];
  semesters: SemPlan[]; electiveNeeded: number; electiveCapacity: number; onTime: boolean;
  totalNeed: number; totalEarned: number; warnings: string[];
};

export const requiredItems = (std: Std): Item[] =>
  std.courses.map((c, i) => ({ ...c, key: `${c.year}-${c.sem}-${i}`, credits: parseFloat(c.credit) || 0 }))
    .filter((c) => REQUIRED.includes(c.type));

export const gradeOf = (cohort: number, currentYear: number) => currentYear - cohort + 1;

/** 從本學期到大四下的剩餘學期 */
export function remainingTerms(grade: number, currentYear: number, currentSem: number): Term[] {
  const out: Term[] = [];
  for (let g = grade; g <= 4; g++) {
    for (const sem of [1, 2]) {
      if (g === grade && sem < currentSem) continue;
      const year = currentYear + (g - grade);
      out.push({ year, sem, label: `${year}-${sem}（大${"一二三四"[g - 1]}${sem === 1 ? "上" : "下"}）` });
    }
  }
  return out;
}

/** 依正常進度估計已修選修學分（使用者可改成實際值） */
export function estimateElectives(std: Std, grade: number, currentSem: number) {
  const done = (grade - 1) * 2 + (currentSem - 1);
  const f = Math.min(done / 8, 1);
  return { pro: Math.round((parseFloat(std.credits[PRO] ?? "0") || 0) * f),
           free: Math.round((parseFloat(std.credits[FREE] ?? "0") || 0) * f) };
}

export function plan(std: Std, x: Inputs): Plan {
  const grade = gradeOf(x.cohort, x.currentYear);
  const items = requiredItems(std);
  const isPast = (c: Item) => +c.year < grade || (+c.year === grade && +c.sem < x.currentSem);
  const past = items.filter(isPast);
  const terms = remainingTerms(grade, x.currentYear, x.currentSem);
  const warnings: string[] = [];
  if (grade < 1 || grade > 4) warnings.push(`入學年 ${x.cohort} 在 ${x.currentYear} 學年不是一到四年級（第 ${grade} 年），以下結果僅供參考。`);

  // 各學期：標準排定的必修＋重修
  const sems: SemPlan[] = terms.map((t) => {
    const g = grade + (t.year - x.currentYear);
    const required = items.filter((c) => +c.year === g && +c.sem === t.sem);
    return { term: t, grade: g, required, retakes: [], requiredCredits: 0, electiveCredits: 0, total: 0,
      min: minCredits(g), max: MAX_CREDITS + x.overload, over: false, overload: false, topUp: 0 };
  });
  for (const c of past.filter((c) => x.failed.has(c.key))) {
    const s = sems.find((s) => s.term.sem === +c.sem);
    if (s) s.retakes.push(c);
    else warnings.push(`「${c.name}」（標準排在${+c.sem === 1 ? "上" : "下"}學期）在剩餘學期中沒有同學期別可重修，可能需要延畢或請系上加開。`);
  }
  for (const s of sems) s.requiredCredits = [...s.required, ...s.retakes].reduce((a, c) => a + c.credits, 0);

  // 學分進度
  const need = (k: string) => parseFloat(std.credits[k] ?? "0") || 0;
  const passedReq = past.filter((c) => !x.failed.has(c.key));
  const categories = Object.entries(CAT).filter(([t]) => REQUIRED.includes(t)).map(([t, name]) => {
    const earned = passedReq.filter((c) => c.type === t).reduce((a, c) => a + c.credits, 0);
    return { name, need: need(name), earned, remaining: Math.max(0, need(name) - earned) };
  }).filter((c) => c.need > 0 || c.earned > 0);
  const proNeed = need(PRO), freeNeed = need(FREE);
  const proRemain = Math.max(0, proNeed - x.proEarned);
  const freeRemain = Math.max(0, freeNeed - x.freeEarned - Math.max(0, x.proEarned - proNeed));
  categories.push({ name: PRO, need: proNeed, earned: x.proEarned, remaining: proRemain });
  if (freeNeed) categories.push({ name: `${FREE}（含專選超出部分）`, need: freeNeed,
    earned: x.freeEarned + Math.max(0, x.proEarned - proNeed), remaining: freeRemain });
  const totalNeed = need(TOTAL);
  const totalEarned = passedReq.reduce((a, c) => a + c.credits, 0) + x.proEarned + x.freeEarned;
  const reqRemaining = sems.reduce((a, s) => a + s.requiredCredits, 0);
  const electiveNeeded = Math.max(proRemain + freeRemain, totalNeed - totalEarned - reqRemaining, 0);

  // 選修平均分配（注水法）：每學期最多填到上限
  let left = electiveNeeded;
  const cap = sems.map((s) => Math.max(0, s.max - s.requiredCredits));
  const electiveCapacity = cap.reduce((a, b) => a + b, 0);
  const alloc = sems.map(() => 0);
  while (left > 1e-9) {
    const open = cap.map((c, i) => (c - alloc[i] > 1e-9 ? i : -1)).filter((i) => i >= 0);
    if (!open.length) break;
    const share = Math.max(1, Math.ceil(left / open.length));
    for (const i of open) {
      const add = Math.min(share, cap[i] - alloc[i], left);
      alloc[i] += add; left -= add;
      if (left <= 1e-9) break;
    }
  }
  sems.forEach((s, i) => {
    s.topUp = Math.max(0, s.min - s.requiredCredits - alloc[i]);
    s.electiveCredits = alloc[i] + s.topUp;
    s.total = s.requiredCredits + s.electiveCredits;
    s.over = s.requiredCredits > s.max;
    s.overload = s.total > MAX_CREDITS;
    if (s.over) warnings.push(`${s.term.label} 光必修與重修就有 ${s.requiredCredits} 學分，超過上限 ${MAX_CREDITS}${x.overload ? `＋超修 ${x.overload}` : ""}，需延後部分課程。`);
    else if (s.overload) warnings.push(`${s.term.label} 合計 ${s.total} 學分，超過 ${MAX_CREDITS}，需申請超修。`);
  });
  const onTime = left <= 1e-9 && !sems.some((s) => s.over) && !warnings.some((w) => w.includes("沒有同學期別"));
  if (left > 1e-9) warnings.push(`剩餘學期的可用學分不足，還差約 ${Math.ceil(left)} 學分 → 依學分上限可能需要延畢（可考慮暑修、超修）。`);
  return { grade, past, categories, semesters: sems, electiveNeeded, electiveCapacity, onTime, totalNeed, totalEarned, warnings };
}
