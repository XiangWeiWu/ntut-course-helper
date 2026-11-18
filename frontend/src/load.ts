/** 每日學習負擔：與 backend/domain/load.py 相同定義（扣分，不是禁止）。
 *  連續上課：節次順序 1 2 3 4 N 5 6 7 8 9 A B C D，空著的 N 視為休息；任何連續 maxConsec+1 節都有課的窗格扣一次。
 *  每日總節數：超過 maxDaily 的每一節扣一次。 */
export const PERIODS = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"];

export type Balance = { maxConsec: number; maxDaily: number; weight: number };
export const DAYS7 = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

export function loadExcess(slots: Set<string>, b: Balance) {
  let consec = 0, daily = 0;
  const perDay: Record<string, number> = {}, longest: Record<string, number> = {};
  for (const d of DAYS7) {
    let n = 0, run = 0, best = 0;
    for (let i = 0; i < PERIODS.length; i++) {
      const on = slots.has(`${d}-${PERIODS[i]}`);
      n += on ? 1 : 0;
      run = on ? run + 1 : 0;
      best = Math.max(best, run);
      if (i + b.maxConsec < PERIODS.length) {
        let all = true;
        for (let j = i; j <= i + b.maxConsec; j++) if (!slots.has(`${d}-${PERIODS[j]}`)) { all = false; break; }
        if (all) consec++;
      }
    }
    perDay[d] = n; longest[d] = best;
    daily += Math.max(0, n - b.maxDaily);
  }
  return { consec_excess: consec, daily_excess: daily, per_day: perDay, longest_run: longest };
}

export const penaltyOf = (slots: Set<string>, b: Balance) => {
  const e = loadExcess(slots, b);
  return b.weight * (e.consec_excess + e.daily_excess);
};
