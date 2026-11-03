import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { todayOf, useMe } from "../../app/useMe";
import { api } from "../../shared/api/client";
import type { Deadline } from "../../shared/api/types";
import { EmptyState, ErrorState, Skeleton } from "../../shared/ui/States";
import { KINDS, date, daysUntil } from "../../shared/ui/format";
import { DaysLeft } from "../inbox/InboxScreen";

function weekOf(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const monday = new Date(d.getTime() - ((d.getUTCDay() + 6) % 7) * 86_400_000);
  return monday.toISOString().slice(0, 10);
}

function Item({ d, today }: { d: Deadline; today: string }) {
  const qc = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => api.confirm(d.id),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <div className="row">
      <DaysLeft due={d.due} today={today} />
      <div>
        <div className="row__who">
          <a href={`#/notice/${d.notice_id}`}>{d.client ?? "Unknown client"}</a>
        </div>
        <div className="row__what">
          {date(d.due)} · {KINDS[d.kind ?? ""] ?? d.kind} · {d.authority} ·{" "}
          {d.basis === "authority" ? "date set by the office" : "objection period"}
        </div>
      </div>
      <div className="row__side">
        {d.status === "confirmed" ? (
          <span className="tag tag--close">Confirmed</span>
        ) : (
          <button
            type="button"
            className="btn btn--ledger"
            disabled={confirm.isPending}
            onClick={() => confirm.mutate()}
          >
            Confirm
          </button>
        )}
        {confirm.isError && <div role="alert">{(confirm.error as Error).message}</div>}
      </div>
    </div>
  );
}

export function DeadlinesScreen() {
  const q = useQuery({ queryKey: ["deadlines"], queryFn: api.deadlines });
  const me = useMe();
  const today = todayOf(me.data);
  return (
    <>
      <h1>Deadline register</h1>
      <p className="lede">
        Every deadline the desk proposes is confirmed by a second person before anyone acts on the notice.
        Where the law leaves the date open, the register holds the earlier one.
      </p>
      {q.isPending ? (
        <Skeleton rows={6} label="Loading deadlines" />
      ) : q.isError ? (
        <ErrorState what="the deadline register" error={q.error} retry={() => q.refetch()} />
      ) : q.data.length === 0 ? (
        <EmptyState title="No running deadlines.">
          <p>
            Deadlines appear here when a notice that can be challenged, or a request with a date, arrives.
          </p>
        </EmptyState>
      ) : (
        <Weeks rows={q.data} today={today} />
      )}
    </>
  );
}

function Weeks({ rows, today }: { rows: Deadline[]; today: string }) {
  const weeks = new Map<string, Deadline[]>();
  for (const r of rows) {
    const w = weekOf(r.due);
    weeks.set(w, [...(weeks.get(w) ?? []), r]);
  }
  const open = rows.filter((r) => r.status === "proposed").length;
  return (
    <>
      <p className="note">
        {rows.length} running, {open} waiting for confirmation
        {rows.some((r) => daysUntil(r.due, today) < 0) ? "; some are past and need attention now" : ""}.
      </p>
      {[...weeks.entries()].map(([w, ds]) => (
        <section key={w} aria-labelledby={`w-${w}`} style={{ marginBottom: "var(--space-5)" }}>
          <h2 id={`w-${w}`}>Week of {date(w)}</h2>
          <div className="list">
            {ds.map((d) => (
              <Item key={d.id} d={d} today={today} />
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
