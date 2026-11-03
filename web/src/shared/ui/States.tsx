import type { ReactNode } from "react";

export function Skeleton({ rows = 4, label }: { rows?: number; label: string }) {
  return (
    <output className="skeleton" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: placeholders have no identity
        <div key={i} />
      ))}
    </output>
  );
}

export function ErrorState({ what, error, retry }: { what: string; error: unknown; retry: () => void }) {
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <div className="alert" role="alert">
      <p>
        <b>Could not load {what}.</b> {msg}
      </p>
      <button type="button" className="btn btn--quiet" onClick={retry}>
        Try again
      </button>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <h2>{title}</h2>
      {children}
    </div>
  );
}
