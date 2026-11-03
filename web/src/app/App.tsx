import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { DeadlinesScreen } from "../features/deadlines/DeadlinesScreen";
import { InboxScreen } from "../features/inbox/InboxScreen";
import { MonitorScreen } from "../features/monitor/MonitorScreen";
import { NoticeScreen } from "../features/notice/NoticeScreen";
import { SignIn } from "../features/session/SignIn";
import { api, setToken } from "../shared/api/client";
import type { Session } from "../shared/api/types";
import { useMe } from "./useMe";

const KEY = "tnd.session";
type Route = { screen: "inbox" | "deadlines" | "monitor" } | { screen: "notice"; id: string };

function parse(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  const [a, b] = h.split("/");
  if (a === "notice" && b) return { screen: "notice", id: decodeURIComponent(b) };
  if (a === "deadlines" || a === "monitor") return { screen: a };
  return { screen: "inbox" };
}

function load(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

const TITLES = {
  inbox: "Incoming notices",
  notice: "Notice",
  deadlines: "Deadline register",
  monitor: "Monitoring",
};

export function App() {
  const [session, setSession] = useState<Session | null>(() => {
    const s = load();
    setToken(s?.token ?? null);
    return s;
  });
  const [route, setRoute] = useState<Route>(parse);
  const qc = useQueryClient();
  useEffect(() => {
    const on = () => setRoute(parse());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    document.title = `${TITLES[route.screen]} · Notice desk`;
  }, [route]);

  const signIn = (s: Session) => {
    setToken(s.token);
    try {
      sessionStorage.setItem(KEY, JSON.stringify(s));
    } catch {
      /* the session lasts until reload */
    }
    window.location.hash = s.person.role === "group_ops" ? "#/monitor" : "#/inbox";
    setSession(s);
  };
  const signOut = () => {
    setToken(null);
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* nothing stored */
    }
    qc.clear();
    setSession(null);
  };
  if (!session) return <SignIn onSignedIn={signIn} />;
  return <Shell session={session} route={route} onSignOut={signOut} />;
}

function Shell({ session, route, onSignOut }: { session: Session; route: Route; onSignOut: () => void }) {
  const me = useMe();
  const firmUser = session.person.role !== "group_ops";
  const open = useQuery({ queryKey: ["inbox"], queryFn: api.inbox, enabled: firmUser });
  const links = [
    ...(firmUser
      ? [
          {
            href: "#/inbox",
            label: "Incoming notices",
            on: route.screen === "inbox" || route.screen === "notice",
            count: open.data?.length,
          },
          { href: "#/deadlines", label: "Deadline register", on: route.screen === "deadlines" },
        ]
      : []),
    { href: "#/monitor", label: "Monitoring", on: route.screen === "monitor" },
  ];
  return (
    <div className="shell">
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="nav">
        <div className="nav__firm">
          {me.data?.firm_name ?? session.person.firm_name ?? "Group"}
          <small>
            Notice desk{me.data?.today ? ` · ${me.data.today.split("-").reverse().join(".")}` : ""}
          </small>
        </div>
        <nav aria-label="Main">
          <ul>
            {links.map((l) => (
              <li key={l.href}>
                <a href={l.href} aria-current={l.on ? "page" : undefined}>
                  <span>{l.label}</span>
                  {l.count !== undefined && <span aria-label={`${l.count} open`}>{l.count}</span>}
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="nav__me">
          {session.person.name}
          <br />
          {roleName(session.person.role)}
          <br />
          <button type="button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>
      <main className="main" id="main">
        {route.screen === "notice" && firmUser ? (
          <NoticeScreen id={route.id} role={session.person.role} />
        ) : route.screen === "deadlines" && firmUser ? (
          <DeadlinesScreen />
        ) : route.screen === "monitor" || !firmUser ? (
          <MonitorScreen />
        ) : (
          <InboxScreen />
        )}
      </main>
    </div>
  );
}

function roleName(r: string) {
  return (
    { clerk: "Clerk", advisor: "Tax adviser", mailroom: "Mailroom", group_ops: "Group operations" }[r] ?? r
  );
}
