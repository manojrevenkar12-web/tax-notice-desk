import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useState } from "react";
import { api } from "../../shared/api/client";
import type { Session } from "../../shared/api/types";
import { ErrorState, Skeleton } from "../../shared/ui/States";

const ROLE = { clerk: "clerk", advisor: "tax adviser", mailroom: "mailroom", group_ops: "group operations" };

export function SignIn({ onSignedIn }: { onSignedIn: (s: Session) => void }) {
  const people = useQuery({ queryKey: ["people"], queryFn: api.people });
  const [person, setPerson] = useState("");
  const signIn = useMutation({ mutationFn: api.signIn, onSuccess: onSignedIn });
  const choices = (people.data ?? []).filter((p) => p.role !== "mailroom");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const id = person || choices[0]?.id;
    if (id) signIn.mutate(id);
  };
  return (
    <main className="signin">
      <h1>Sign in</h1>
      <p className="lede">Development sign-in. In production each firm's identity provider signs staff in.</p>
      <form onSubmit={submit}>
        <label htmlFor="person">Person</label>
        {people.isPending ? (
          <Skeleton rows={1} label="Loading people" />
        ) : people.isError ? (
          <ErrorState what="the people of the group" error={people.error} retry={() => people.refetch()} />
        ) : (
          <select id="person" value={person || choices[0]?.id} onChange={(e) => setPerson(e.target.value)}>
            {choices.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}, {ROLE[p.role]}
                {p.firm_name ? ` at ${p.firm_name}` : ""}
              </option>
            ))}
          </select>
        )}
        {signIn.isError && <p role="alert">Sign-in failed: {(signIn.error as Error).message}</p>}
        <div className="actions">
          <button type="submit" className="btn" disabled={signIn.isPending || !choices.length}>
            {signIn.isPending ? "Signing in…" : "Sign in"}
          </button>
        </div>
      </form>
    </main>
  );
}
