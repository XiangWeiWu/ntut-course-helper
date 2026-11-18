import { DAYS, DAY_ZH, PERIODS, type Course } from "../api";

export default function Timetable({ courses, onRemove }: { courses: Course[]; onRemove?: (id: string) => void }) {
  const days = DAYS.filter((d) => d !== "sun" && (d !== "sat" || courses.some((c) => c.time.sat?.length)));
  const cell = (d: string, p: string) => courses.filter((c) => c.time[d]?.includes(p));
  const used = PERIODS.filter((p) => ["1","2","3","4","5","6","7","8","9"].includes(p) || courses.some((c) => days.some((d) => c.time[d]?.includes(p))));
  return (
    <div className="scroll">
      <table className="tt">
        <thead><tr><th style={{ width: 34 }}>節</th>{days.map((d) => <th key={d}>{DAY_ZH[d]}</th>)}</tr></thead>
        <tbody>
          {used.map((p) => (
            <tr key={p}>
              <th>{p}</th>
              {days.map((d) => {
                const cs = cell(d, p);
                return (
                  <td key={d} className={cs.length > 1 ? "conflict" : cs.length ? "filled" : ""} title={cs.map((c) => c.name).join(" / ")}>
                    {cs.map((c) => (
                      <div key={c.id} onClick={() => onRemove?.(c.id)} style={{ cursor: onRemove ? "pointer" : undefined, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {c.name}
                      </div>
                    ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
