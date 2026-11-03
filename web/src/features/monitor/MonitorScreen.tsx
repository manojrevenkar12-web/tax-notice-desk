import { useQuery } from "@tanstack/react-query";
import { api } from "../../shared/api/client";
import type { Monitor } from "../../shared/api/types";
import { EmptyState, ErrorState, Skeleton } from "../../shared/ui/States";
import { ACTIONS, FIELDS } from "../../shared/ui/format";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "–" : `${(v * 100).toFixed(1)} %`;

function Quality({ q, split, label }: { q: Monitor["quality"]; split: string; label: string }) {
  const m = q[split];
  if (!m) return null;
  return (
    <section aria-labelledby={`q-${split}`} style={{ marginBottom: "var(--space-5)" }}>
      <h2 id={`q-${split}`}>{label}</h2>
      <div className="tiles">
        <div className="tile">
          <b>{m.late_deadlines ?? "–"}</b>
          <span>deadlines later than the real one</span>
        </div>
        <div className="tile">
          <b>{m.closed_but_needed_action ?? "–"}</b>
          <span>notices closed that needed action</span>
        </div>
        <div className="tile">
          <b>{pct(m.deadline_exact)}</b>
          <span>deadlines exactly right</span>
        </div>
        <div className="tile">
          <b>{pct(m.auto_close_rate)}</b>
          <span>of matching notices recorded without a person</span>
        </div>
        <div className="tile">
          <b>{pct(m.review_rate)}</b>
          <span>of notices a person had to read first</span>
        </div>
        <div className="tile">
          <b>{pct(m.error_recall)}</b>
          <span>of errors on notices caught</span>
        </div>
      </div>
    </section>
  );
}

export function MonitorScreen() {
  const q = useQuery({ queryKey: ["monitor"], queryFn: api.monitor });
  return (
    <>
      <h1>Monitoring</h1>
      <p className="lede">
        How the desk is doing per firm, and how it did on months nobody tuned it on. No client data.
      </p>
      {q.isPending ? (
        <Skeleton rows={4} label="Loading monitoring" />
      ) : q.isError ? (
        <ErrorState what="monitoring" error={q.error} retry={() => q.refetch()} />
      ) : q.data.firms.length === 0 ? (
        <EmptyState title="No firms yet." />
      ) : (
        <View m={q.data} />
      )}
    </>
  );
}

function View({ m }: { m: Monitor }) {
  const actions = Object.keys(ACTIONS) as (keyof typeof ACTIONS)[];
  return (
    <>
      <Quality q={m.quality} split="test" label="Test month (release gate)" />
      <Quality q={m.quality} split="heldout" label="Held-out month, run once" />
      <section aria-labelledby="firms-h" className="panel">
        <h2 id="firms-h">Notices per firm</h2>
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Firm</th>
                {actions.map((a) => (
                  <th key={a} scope="col" className="num">
                    {ACTIONS[a].label}
                  </th>
                ))}
                <th scope="col" className="num">
                  Deadlines waiting
                </th>
              </tr>
            </thead>
            <tbody>
              {m.firms.map((f) => (
                <tr key={f.id}>
                  <th scope="row">{f.name}</th>
                  {actions.map((a) => (
                    <td key={a} className="num">
                      {m.actions.find((x) => x.firm_id === f.id && x.action === a)?.notices ?? 0}
                    </td>
                  ))}
                  <td className="num">{m.deadlines.find((x) => x.firm_id === f.id)?.proposed ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-labelledby="cor-h" className="panel">
        <h2 id="cor-h">What people corrected</h2>
        {m.corrections.length === 0 ? (
          <p className="note">
            No corrections yet. Each correction of a town's notice teaches the desk that town's labels.
          </p>
        ) : (
          <ul>
            {m.corrections.map((c) => (
              <li key={`${c.firm_id}-${c.field}`}>
                {FIELDS[c.field] ?? c.field}: {c.corrections}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
