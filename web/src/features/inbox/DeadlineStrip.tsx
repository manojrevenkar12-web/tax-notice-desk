import type { CSSProperties } from "react";
import type { InboxRow } from "../../shared/api/types";
import { SOON_DAYS, daysUntil } from "../../shared/ui/format";

const DAYS = 35;

/** The next five weeks, one column per day; each open deadline is a mark on its day. */
export function DeadlineStrip({ rows, today }: { rows: InboxRow[]; today: string }) {
  const start = new Date(`${today}T00:00:00Z`);
  const days = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(start.getTime() + i * 86_400_000);
    return d.toISOString().slice(0, 10);
  });
  const by: Record<string, InboxRow[]> = {};
  for (const r of rows) {
    if (r.due) by[r.due] = [...(by[r.due] ?? []), r];
  }
  const overdue = rows.filter((r) => r.due && daysUntil(r.due, today) < 0).length;
  const within = rows.filter(
    (r) => r.due && daysUntil(r.due, today) >= 0 && daysUntil(r.due, today) < DAYS,
  ).length;
  return (
    <section aria-label="Deadlines in the next five weeks">
      <div className="strip" aria-hidden="true">
        {days.map((d, i) => {
          const wd = new Date(`${d}T00:00:00Z`).getUTCDay();
          return (
            <div key={d} className={`strip__day ${wd === 0 || wd === 6 ? "strip__day--free" : ""}`} title={d}>
              {(by[d] ?? []).map((r) => (
                <span
                  key={r.id}
                  className={`strip__mark ${r.deadline_status === "confirmed" ? "strip__mark--confirmed" : i <= SOON_DAYS ? "strip__mark--soon" : ""}`}
                />
              ))}
              {(i === 0 || d.endsWith("-01") || i % 7 === 0) && (
                <span
                  className={`strip__label ${i === 0 ? "strip__label--first" : ""}`}
                >{`${d.slice(8, 10)}.${d.slice(5, 7)}.`}</span>
              )}
            </div>
          );
        })}
      </div>
      <p className="strip-legend">
        <span style={{ "--c": "var(--stamp)" } as CSSProperties}>within {SOON_DAYS} days</span>
        <span style={{ "--c": "var(--navy)" } as CSSProperties}>later, not yet confirmed</span>
        <span style={{ "--c": "var(--ledger)" } as CSSProperties}>confirmed by a second person</span>
        <span>
          {within} deadlines in the next five weeks{overdue ? `, ${overdue} overdue` : ""}
        </span>
      </p>
    </section>
  );
}
