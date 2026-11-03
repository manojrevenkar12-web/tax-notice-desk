import type { Deadline, InboxRow, Me, Monitor, Notice, Person, Session } from "./types";

let token: string | null = null;
export const setToken = (t: string | null) => {
  token = t;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      const d = body.detail ?? body.title;
      detail = typeof d === "string" ? d : (d?.title ?? JSON.stringify(d));
    } catch {
      /* not JSON */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

const post = <T>(path: string, body: unknown) =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  people: () => call<Person[]>("/api/dev/people"),
  signIn: (person: string) => post<Session>("/api/dev/sign-in", { person }),
  me: () => call<Me>("/api/me"),
  inbox: () => call<InboxRow[]>("/api/inbox"),
  notice: (id: string) => call<Notice>(`/api/notices/${id}`),
  deadlines: () => call<Deadline[]>("/api/deadlines"),
  confirm: (id: number) => post<{ ok: boolean }>(`/api/deadlines/${id}/confirm`, {}),
  decide: (id: string, outcome: string) => post<{ ok: boolean }>(`/api/notices/${id}/decision`, { outcome }),
  release: (id: number, text?: string) => post<{ ok: boolean }>(`/api/drafts/${id}/release`, { text }),
  monitor: () => call<Monitor>("/api/monitor"),
  pageUrl: (id: string) => `/api/notices/${id}/page.png`,
};

export async function pageBlob(id: string): Promise<string> {
  const r = await fetch(api.pageUrl(id), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new ApiError(r.status, "page not available");
  return URL.createObjectURL(await r.blob());
}
