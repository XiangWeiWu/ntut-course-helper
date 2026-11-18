/**
 * 解析課程標準中的畢業規定文字（standard.rules）。純計算，可用 node 測試。
 *
 * 1. 通識（博雅）：「通識博雅課程應修滿15學分，其中「A」、「B」及「C」等三大向度為…指定向度課程，
 *    以上每向度至少需選修4學分…；另餘3學分，學生可不分向度任選」→ { total, dims, perDim, free }
 *    （112–115 學年四技 160 條中 160 條可解析；「須／需」兩種寫法都支援）
 * 2. 課群：「A、B、C 3門課至少須選修其中2門」「「A」、「B」…等9門…至少需修習1門」→ { names, k }
 *    作法：不依賴分隔符號，直接在句中找「課程標準裡存在的課名」（長名優先，避免把「物理化學(二)」誤認成「物理」），
 *    再抓「至少 K 門」。對到 2 門以上才算可自動檢查。
 * 3. 其他（英文畢業門檻、跨領域學程、以 ※ 等符號指定的課群——符號在資料中已被去掉）→ 人工勾選項目。
 */
export type GenEd = { total: number; dims: string[]; perDim: number; free: number; freeCap?: number; text: string };
export type Group = { text: string; names: string[]; k: number;
  declared?: number;   // 規則文字寫的門數（如「下列五門課」「等9門」）；> names.length 表示有課名在標準中找不到
};
export type Manual = { id: string; text: string };
export type Rules = { genEd?: GenEd; groups: Group[]; manual: Manual[]; all: string[] };

const CN: Record<string, number> = { 一: 1, 二: 2, 兩: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
const num = (s: string) => (/^\d+$/.test(s) ? +s : CN[s] ?? NaN);
/** 正規化：全形括號→半形、去空白、去掉「(2下)」這類學期註記 */
export const norm = (s: string) => s.replace(/（/g, "(").replace(/）/g, ")").replace(/\s+/g, "")
  .replace(/\([1-4][上下]\)/g, "");

export function parseGenEd(rules: string[]): GenEd | undefined {
  for (const r of rules) {
    const m = r.match(/博雅課程應修滿(\d+)學分.*?其中(.+?)等.大向度.*?每向度至少[須需]?選修(\d+)學分.*?另餘(\d+)學分/);
    if (!m) continue;
    const dims = [...m[2].matchAll(/「(.+?)」/g)].map((x) => x[1]);
    const capRule = rules.find((x) => /通識博雅課程至多認列\d+學分/.test(x));
    const cap = capRule?.match(/通識博雅課程至多認列(\d+)學分/);
    return { total: +m[1], dims, perDim: +m[3], free: +m[4], freeCap: cap ? +cap[1] : undefined, text: r };
  }
  return undefined;
}

/** 在句子中找出課程標準裡的課名（長名優先、不重疊） */
export function findNames(clause: string, names: string[]): string[] {
  const text = norm(clause);
  const uniq = [...new Set(names.map(norm))].filter((n) => n.length >= 2).sort((a, b) => b.length - a.length);
  const used = new Array(text.length).fill(false);
  const found: { n: string; at: number }[] = [];
  for (const n of uniq) {
    let from = 0;
    while (true) {
      const at = text.indexOf(n, from);
      if (at < 0) break;
      if (!used.slice(at, at + n.length).some(Boolean)) {
        for (let i = at; i < at + n.length; i++) used[i] = true;
        found.push({ n, at });
        break;
      }
      from = at + 1;
    }
  }
  return found.sort((a, b) => a.at - b.at).map((x) => x.n);
}

/** courses：課程標準的課（含 type）。課群只看選修課（例：分子系「除了必修之…外，至少修習三門選修實驗」）。 */
export function parseRules(rules: string[] | null | undefined, courses: { name: string; type: string }[]): Rules {
  const electiveNames = courses.filter((c) => !["○", "△", "●", "▲"].includes(c.type)).map((c) => c.name);
  const all = (rules ?? []).map((r) => r.trim()).filter(Boolean);
  const genEd = parseGenEd(all);
  const groups: Group[] = [];
  const manual: Manual[] = [];
  const addManual = (text: string) => { if (!manual.some((m) => m.text === text)) manual.push({ id: `m${manual.length}`, text }); };
  for (const r of all) {
    if (genEd && r === genEd.text) continue;
    if (/英文畢業門檻|英文能力/.test(r)) { addManual(r); continue; }
    if (/微學程|一般學程|第二專長|輔系|雙主修/.test(r) && /畢業前須|須修畢/.test(r)) { addManual(r); continue; }
    if (!/至少/.test(r)) {
      if (/永續公民實踐/.test(r)) addManual("需修習「永續公民實踐」始可畢業。");
      continue;
    }
    if (/下列.{0,4}項.*其中.項/.test(r) || /[※*＊]表示|學域分類|核心組別/.test(r)) { addManual(r); continue; }
    // 以每個「至少 K 門／之其中 K 門」的位置切段：每段只取「上一個門檻之後、到這個門檻為止」的課名
    // （同一句可能用「；」或「，」接好幾個課群，例如材資系 3選2、2選1、3選1）
    const re = /(?:之其中|至少[^0-9一二三四五六七八九十兩]{0,8}?)\s*([0-9一二三四五六七八九十兩]+)\s*門/g;
    let prev = 0, found = 0;
    for (const m of r.matchAll(re)) {
      const end = (m.index ?? 0) + m[0].length;
      const seg = r.slice(prev, end);          // 沒找到課群的段落不切斷，併入下一段（保留「下列五門」這類資訊）
      const names = findNames(seg, electiveNames);
      const k = num(m[1]);
      if (names.length >= 2 && k >= 1 && k <= names.length) {
        const d = seg.match(/(?:下列|等)\s*([0-9一二三四五六七八九十兩]+)\s*門|([0-9一二三四五六七八九十兩]+)\s*門課/);
        const declared = d ? num(d[1] ?? d[2]) : undefined;
        groups.push({ text: seg.replace(/^[，。；、\s]+/, ""), names, k,
          declared: declared && declared > names.length ? declared : undefined });
        found++;
        prev = end;
      }
    }
    if (!found) addManual(r);
  }
  return { genEd, groups, manual, all };
}
