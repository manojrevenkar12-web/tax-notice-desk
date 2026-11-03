import { useQuery } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useState } from "react";
import { todayOf, useMe } from "../../app/useMe";
import { api } from "../../shared/api/client";
import type { Action, InboxRow } from "../../shared/api/types";
import { EmptyState, ErrorState, Skeleton } from "../../shared/ui/States";
import { ACTIONS, KINDS, SOON_DAYS, daysUntil, signed } from "../../shared/ui/format";
import { DeadlineStrip } from "./DeadlineStrip";

const BUCKETS: { id: string; label: string; actions: Action[] }[] = [
  { id: "act", label: "To act on", actions: ["objection_required", "objection_review", "task", "review"] },
  { id: "inform", label: "Tell the client", actions: ["inform_client"] },
  { id: "closed", label: "Matches the return", actions: ["close"] },
  { id: "other", label: "Copies and not ours", actions: ["duplicate", "misrouted"] },
];

export function DaysLeft({ due, today }: { due: string | null; today: string }) {
  if (!due)
    return (
      <div className="days days--none" aria-label="No deadline">
        <b>–</b>
        <small>no date</small>
      </div>
    );
  const d = daysUntil(due, today);
  return (
    <div className={`days ${d <= SOON_DAYS ? "days--soon" : ""}`} aria-label={`${d} days left`}>
      <b>{d}</b>
      <small>{d === 1 ? "day" : "days"}</small>
    </div>
  );
}

function Row({ n, today }: { n: InboxRow; today: string }) {
  return (
    <a className="row" href={`#/notice/${n.id}`}>
      <DaysLeft due={n.due} today={today} />
      <div>
        <div className="row__who">{n.client ?? "Unknown client"}</div>
        <div className="row__what">
          {KINDS[n.kind ?? ""] ?? "Unrecognised notice"}
          {n.tax_year ? ` ${n.tax_year}` : ""} · {n.authority ?? "unknown authority"}
          {n.deadline_status === "proposed" && " · deadline not yet confirmed"}
        </div>
      </div>
      <div className="row__side">
        <span className={`tag tag--${n.action}`}>{ACTIONS[n.action].label}</span>
        {n.tax_effect !== 0 && <div className="muted">{signed(n.tax_effect)}</div>}
      </div>
    </a>
  );
}

export function InboxScreen() {
  const q = useQuery({ queryKey: ["inbox"], queryFn: api.inbox });
  const me = useMe();
  const today = todayOf(me.data);
  const [bucket, setBucket] = useState("act");
  return (
    <>
      <h1>Incoming notices</h1>
      <p className="lede">
        Every notice is read, matched to a client, checked against the filed return and given a deadline. What
        matches is recorded; everything else waits here, soonest deadline first.
      </p>
      {q.isPending ? (
        <Skeleton rows={5} label="Loading notices" />
      ) : q.isError ? (
        <ErrorState what="the notices" error={q.error} retry={() => q.refetch()} />
      ) : q.data.length === 0 ? (
        <EmptyState title="No open notices.">
          <p>New mail is read as it arrives. The deadline register lists what is still running.</p>
        </EmptyState>
      ) : (
        <>
          <DeadlineStrip rows={q.data} today={today} />
          <fieldset className="tabs" aria-label="Show">
            {BUCKETS.map((b) => {
              const n = q.data.filter((r) => b.actions.includes(r.action)).length;
              return (
                <button
                  key={b.id}
                  type="button"
                  aria-pressed={bucket === b.id}
                  onClick={() => setBucket(b.id)}
                >
                  {b.label} · {n}
                </button>
              );
            })}
          </fieldset>
          <Bucket
            rows={q.data.filter((r) => BUCKETS.find((b) => b.id === bucket)?.actions.includes(r.action))}
            today={today}
          />
        </>
      )}
    </>
  );
}

function Bucket({ rows, today }: { rows: InboxRow[]; today: string }) {
  if (!rows.length)
    return (
      <EmptyState title="Nothing in this group.">
        <p>The other groups may still hold notices.</p>
      </EmptyState>
    );
  return (
    <div className="list">
      {rows.map((n, i) => (
        <motion.div
          key={n.id}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: Math.min(i, 12) * 0.015 }}
        >
          <Row n={n} today={today} />
        </motion.div>
      ))}
    </div>
  );
}
