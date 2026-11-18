export type Course = {
  id: string; code?: string; name: string; nameEn: string; credit: number; type: string; typeName: string;
  classes: string[]; teachers: string[]; classrooms: string[]; time: Record<string, string[]>;
  people: number; capacity: number; capacitySource: string; language: string; notes: string; description?: string;
};
export const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export const DAY_ZH: Record<string, string> = { sun: "日", mon: "一", tue: "二", wed: "三", thu: "四", fri: "五", sat: "六" };
export const PERIODS = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"];

export async function get<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}
export async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText);
  return r.json();
}
export const slotKeys = (c: Course) => Object.entries(c.time).flatMap(([d, ps]) => ps.map((p) => `${d}-${p}`));
export const timeText = (c: Course) =>
  DAYS.filter((d) => c.time[d]?.length).map((d) => `${DAY_ZH[d]}${c.time[d].join("")}`).join(" ") || "未排時間";
