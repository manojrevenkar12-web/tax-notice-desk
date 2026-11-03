export type Action =
  | "close"
  | "inform_client"
  | "objection_review"
  | "objection_required"
  | "task"
  | "duplicate"
  | "misrouted"
  | "review";

export interface Person {
  id: string;
  name: string;
  role: "clerk" | "advisor" | "mailroom" | "group_ops";
  firm: string | null;
  firm_name: string | null;
}

export interface Me {
  person: string;
  firm: string | null;
  role: string;
  today: string;
  firm_name: string;
  city: string;
}

export interface Session {
  token: string;
  person: Person;
}

export interface InboxRow {
  id: string;
  kind: string | null;
  tax_year: number | null;
  authority: string | null;
  notice_date: string | null;
  action: Action;
  reasons: string[];
  status: string;
  tax_effect: number;
  client_id: string | null;
  client: string | null;
  due: string | null;
  deadline_status: string | null;
  deadline_id: number | null;
  verified: boolean;
  channel: string;
}

export interface Finding {
  type: string;
  field: string | null;
  filed: number | null;
  stated: number | null;
  expected: number | null;
  against: boolean | null;
  primary: boolean;
  detail: string;
  sources: string[];
}

export interface Hit {
  id: string;
  kind: string;
  ref: string;
  paragraph: string | null;
  title: string;
  text: string;
  why: string;
  stale: string | null;
  source: string;
}

export interface Explanation {
  finding: Finding;
  what: string;
  office_says: string | null;
  unexplained: boolean;
  law: Hit[];
  playbook: Hit[];
  history: Hit[];
  sources: string[];
}

export interface Deadline {
  id: number;
  due: string;
  bekanntgabe: string;
  basis: string;
  rules: string[];
  notes: string[];
  later_possible: string | null;
  status: "proposed" | "confirmed" | "done" | "cancelled";
  proposed_by: string;
  confirmed_by: string | null;
  kind?: string;
  action?: Action;
  authority?: string;
  client?: string;
  notice_id: string;
}

export interface Draft {
  id: number;
  kind: string;
  text: string;
  citations: string[];
  verification: { ok: boolean; unknown_sections: string[]; unknown_amounts: string[]; problems: string[] };
  written_by: string;
  status: "draft" | "released";
}

export interface Notice {
  id: string;
  kind: string | null;
  tax_year: number | null;
  authority: string | null;
  notice_date: string | null;
  action: Action;
  reasons: string[];
  status: string;
  outcome: string | null;
  client: string | null;
  steuernummer: string | null;
  tax_effect: number;
  parsed: {
    fields: Record<string, number>;
    method: Record<string, string>;
    verified: boolean;
    failed_checks: string[];
    vorbehalt: boolean;
    vorlaeufig: string[];
    remedy: string | null;
    explanations: string[];
    source: string;
  };
  filed: Record<string, number> | null;
  findings: Finding[];
  explanation: Explanation[];
  deadlines: Deadline[];
  drafts: Draft[];
  document: { channel: string; received_at: string; meta: Record<string, string> } | null;
  history: { year: number; kind: string; text: string; objection: boolean; outcome: string | null }[];
}

export interface Monitor {
  firms: { id: string; name: string; city: string }[];
  actions: { firm_id: string; action: Action; notices: number; open: number }[];
  deadlines: { firm_id: string; proposed: number; confirmed: number; done: number }[];
  corrections: { firm_id: string; field: string; corrections: number }[];
  quality: Record<string, Record<string, number | null>>;
}
