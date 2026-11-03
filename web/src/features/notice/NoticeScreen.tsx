import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { todayOf, useMe } from "../../app/useMe";
import { api, pageBlob } from "../../shared/api/client";
import type { Deadline, Draft, Explanation, Notice } from "../../shared/api/types";
import { ErrorState, Skeleton } from "../../shared/ui/States";
import { ACTIONS, FIELDS, KINDS, SOON_DAYS, date, daysUntil, money, signed } from "../../shared/ui/format";

const MONTHS = ["JAN", "FEB", "MÄR", "APR", "MAI", "JUN", "JUL", "AUG", "SEP", "OKT", "NOV", "DEZ"];

function Stamp({ iso }: { iso: string }) {
  const [y, m, d] = iso.split("-");
  return (
    <div className="stamp" aria-label={`Received ${date(iso)}`}>
      <small>Eingang</small>
      {d} {MONTHS[Number(m) - 1]} {y}
    </div>
  );
}

function Page({ id }: { id: string }) {
  const q = useQuery({
    queryKey: ["page", id],
    queryFn: () => pageBlob(id),
    staleTime: Number.POSITIVE_INFINITY,
  });
  if (q.isPending) return <Skeleton rows={6} label="Loading the page" />;
  if (q.isError) return <p className="muted">The page image is not available.</p>;
  return <img src={q.data} alt="First page of the notice as received" />;
}

function DeadlineCard({ d, today, canConfirm }: { d: Deadline; today: string; canConfirm: boolean }) {
  const qc = useQueryClient();
  const confirm = useMutation({
    mutationFn: () => api.confirm(d.id),
    onSuccess: () => qc.invalidateQueries(),
  });
  const left = daysUntil(d.due, today);
  const cls = d.status === "confirmed" ? "is-confirmed" : left <= SOON_DAYS ? "is-soon" : "";
  return (
    <section className={`panel panel--deadline ${cls}`} aria-labelledby="dl-h">
      <h2 id="dl-h">
        Deadline {date(d.due)} · {left} days
      </h2>
      <dl className="facts">
        <div>
          <dt>Counts as received</dt>
          <dd>{date(d.bekanntgabe)}</dd>
        </div>
        <div>
          <dt>Basis</dt>
          <dd>{d.basis === "authority" ? "date set by the office" : "objection period"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{d.status === "confirmed" ? "confirmed by a second person" : "proposed by the desk"}</dd>
        </div>
      </dl>
      <p className="note">Rules: {d.rules.join(" · ")}</p>
      {d.notes.map((n) => (
        <p key={n} className="warn">
          {n}
        </p>
      ))}
      {d.later_possible && (
        <p className="note">
          A later date ({date(d.later_possible)}) may be arguable; the register keeps the earlier one.
        </p>
      )}
      {d.status === "proposed" && (
        <div className="actions">
          <button
            type="button"
            className="btn btn--ledger"
            disabled={!canConfirm || confirm.isPending}
            onClick={() => confirm.mutate()}
          >
            {confirm.isPending ? "Confirming…" : "Confirm deadline"}
          </button>
          {confirm.isError && <span role="alert">{(confirm.error as Error).message}</span>}
        </div>
      )}
    </section>
  );
}

function Comparison({ n }: { n: Notice }) {
  const f = n.parsed.fields;
  const keys = [
    ...Object.keys(FIELDS).filter((k) => k in f),
    ...Object.keys(f).filter((k) => !(k in FIELDS)),
  ];
  const devs = new Map(n.findings.filter((x) => x.type === "deviation").map((x) => [x.field, x]));
  if (!keys.length) return null;
  return (
    <section className="panel" aria-labelledby="cmp-h">
      <h2 id="cmp-h">{n.filed ? "Notice against the filed return" : "Values on the notice"}</h2>
      {!n.parsed.verified && (
        <p className="warn">
          Not confirmed: {n.parsed.failed_checks.join(", ") || "the notice's arithmetic does not hold"}. Read
          the page and correct the values before acting.
        </p>
      )}
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Figure</th>
              {n.filed && (
                <th scope="col" className="num">
                  Filed
                </th>
              )}
              <th scope="col" className="num">
                Notice
              </th>
              <th scope="col">Read from</th>
              {n.filed && (
                <th scope="col" className="num">
                  Difference
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => {
              const dv = devs.get(k);
              const diff = n.filed && n.filed[k] !== undefined ? f[k] - n.filed[k] : null;
              return (
                <tr key={k} className={`${dv ? "is-diff" : ""} ${dv?.against ? "is-against" : ""}`}>
                  <th scope="row">{FIELDS[k] ?? k}</th>
                  {n.filed && <td className="num">{money(n.filed[k])}</td>}
                  <td className="num">{k === "hebesatz" ? `${f[k] / 100} %` : money(f[k])}</td>
                  <td>{n.parsed.method[k] ?? "–"}</td>
                  {n.filed && <td className="num">{diff ? signed(diff) : "–"}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function FindingItem({ e }: { e: Explanation }) {
  return (
    <div className="finding">
      <h3>{e.what}</h3>
      {e.unexplained ? (
        <p className="warn">The office gives no reason for this change.</p>
      ) : (
        e.office_says && <p className="quote">{e.office_says}</p>
      )}
      {e.law.slice(0, 2).map((h) => (
        <details key={h.id}>
          <summary>
            {h.ref} {h.paragraph ?? ""} · {h.title}
          </summary>
          <p className="law">{h.text}</p>
          {h.stale && (
            <p className="warn">
              This copy is outdated for the tax year: {h.stale}. Cite the version in force.
            </p>
          )}
          <p className="note">{h.source}</p>
        </details>
      ))}
      {e.playbook.slice(0, 1).map((h) => (
        <details key={h.id}>
          <summary>Firm playbook: {h.title}</summary>
          <p className="law">{h.text}</p>
        </details>
      ))}
      {e.history.length > 0 && (
        <p className="note">Before for this client: {e.history.map((h) => h.text).join(" · ")}</p>
      )}
    </div>
  );
}

function DraftPanel({ d, canRelease }: { d: Draft; canRelease: boolean }) {
  const qc = useQueryClient();
  const [text, setText] = useState(d.text);
  const release = useMutation({
    mutationFn: () => api.release(d.id, text),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <section className="panel" aria-labelledby="draft-h">
      <h2 id="draft-h">Objection draft</h2>
      <p className="note">
        Written by{" "}
        {d.written_by === "template"
          ? "the desk's template"
          : `the model (${d.written_by}), checked by the verifier`}
        . Every section and amount must be one the desk can back; the verifier runs again on release.
      </p>
      <label className="muted" htmlFor="draft-text">
        Draft text
      </label>
      <textarea
        id="draft-text"
        className="draft"
        value={text}
        readOnly={d.status === "released" || !canRelease}
        onChange={(e) => setText(e.target.value)}
      />
      {d.status === "released" ? (
        <p className="okay">Released.</p>
      ) : (
        <div className="actions">
          <button
            type="button"
            className="btn"
            disabled={!canRelease || release.isPending}
            onClick={() => release.mutate()}
          >
            {release.isPending ? "Checking…" : "Release draft"}
          </button>
          {!canRelease && <span className="note">Only a tax adviser releases an objection.</span>}
          {release.isError && <span role="alert">{(release.error as Error).message}</span>}
        </div>
      )}
    </section>
  );
}

function Decision({ n, role }: { n: Notice; role: string }) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: (o: string) => api.decide(n.id, o),
    onSuccess: () => qc.invalidateQueries(),
  });
  if (n.status === "done") return <p className="okay">Done: {n.outcome?.replace("_", " ")}.</p>;
  const objection = n.action === "objection_review" || n.action === "objection_required";
  const options = objection
    ? [
        ["objection_filed", "Objection filed"],
        ["no_objection", "No objection"],
      ]
    : n.action === "task"
      ? [["task_done", "Done"]]
      : n.action === "duplicate"
        ? [["duplicate", "Set aside copy"]]
        : n.action === "close"
          ? [["close", "Record as matching"]]
          : [["inform_client", "Client informed"]];
  return (
    <section className="panel" aria-labelledby="dec-h">
      <h2 id="dec-h">Decision</h2>
      <p className="note">
        {ACTIONS[n.action].plain}. {n.reasons.join("; ")}.
      </p>
      <div className="actions">
        {options.map(([o, label]) => (
          <button
            key={o}
            type="button"
            className="btn btn--quiet"
            disabled={decide.isPending || (objection && role !== "advisor")}
            onClick={() => decide.mutate(o)}
          >
            {label}
          </button>
        ))}
      </div>
      {objection && role !== "advisor" && <p className="note">An objection is decided by a tax adviser.</p>}
      {decide.isError && (
        <p role="alert" className="warn">
          {(decide.error as Error).message}
        </p>
      )}
    </section>
  );
}

export function NoticeScreen({ id, role }: { id: string; role: string }) {
  const q = useQuery({ queryKey: ["notice", id], queryFn: () => api.notice(id) });
  const me = useMe();
  const today = todayOf(me.data);
  useEffect(() => window.scrollTo(0, 0), []);
  if (q.isPending) return <Skeleton rows={6} label="Loading the notice" />;
  if (q.isError) return <ErrorState what="the notice" error={q.error} retry={() => q.refetch()} />;
  const n = q.data;
  const d = n.deadlines.find((x) => x.status !== "cancelled");
  return (
    <>
      <p>
        <a href="#/inbox">Back to incoming notices</a>
      </p>
      <h1>
        {n.client ?? "Unknown client"}: {KINDS[n.kind ?? ""] ?? "notice"} {n.tax_year ?? ""}
      </h1>
      <p className="lede">
        {n.authority} · notice of {date(n.notice_date)} · tax number {n.steuernummer ?? "–"} ·{" "}
        <span className={`tag tag--${n.action}`}>{ACTIONS[n.action].label}</span>
        {n.parsed.vorbehalt && " · under § 164 AO (Vorbehalt der Nachprüfung)"}
      </p>
      <div className="detail">
        <div className="sheet">
          {n.document && <Stamp iso={n.document.received_at.slice(0, 10)} />}
          <Page id={n.id} />
        </div>
        <div>
          <AnimatePresence initial={false}>
            <motion.div key={n.status} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              {d ? (
                <DeadlineCard d={d} today={today} canConfirm={role === "clerk" || role === "advisor"} />
              ) : null}
              <Decision n={n} role={role} />
            </motion.div>
          </AnimatePresence>
          <Comparison n={n} />
          {n.explanation.length > 0 && (
            <section className="panel" aria-labelledby="why-h">
              <h2 id="why-h">What differs and why</h2>
              {n.explanation.map((e) => (
                <FindingItem key={`${e.finding.type}-${e.finding.field}`} e={e} />
              ))}
            </section>
          )}
          {n.drafts.map((dr) => (
            <DraftPanel key={dr.id} d={dr} canRelease={role === "advisor"} />
          ))}
        </div>
      </div>
    </>
  );
}
