import type { Action } from "../api/types";

const euro = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

export function money(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return "–";
  return euro.format(cents / 100);
}

export function signed(cents: number): string {
  return `${cents > 0 ? "+" : ""}${money(cents)}`;
}

export function date(iso: string | null | undefined): string {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

/** Whole days from `today` to `iso`, both as calendar dates. */
export function daysUntil(iso: string, today: string): number {
  const a = Date.UTC(+today.slice(0, 4), +today.slice(5, 7) - 1, +today.slice(8, 10));
  const b = Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
  return Math.round((b - a) / 86_400_000);
}

export const SOON_DAYS = 7;

export const ACTIONS: Record<Action, { label: string; plain: string }> = {
  objection_required: { label: "Object", plain: "The notice is wrong on its face" },
  objection_review: { label: "Decide on objection", plain: "Deviates from the return against the client" },
  review: { label: "Read first", plain: "The desk could not confirm the values" },
  task: { label: "Task", plain: "The office expects something by a date" },
  inform_client: { label: "Tell the client", plain: "Nothing to object to" },
  close: { label: "Matches", plain: "Same as the filed return, every check passed" },
  duplicate: { label: "Copy", plain: "Already on the desk" },
  misrouted: { label: "Not ours", plain: "No client of the group has this tax number" },
};

export const KINDS: Record<string, string> = {
  est: "Income tax",
  kst: "Corporate tax",
  ust: "VAT",
  gewst_mess: "Trade tax base",
  gewst: "Trade tax (town)",
  vz_est: "Prepayments",
  request: "Request for documents",
  reminder: "Missing return",
  audit: "Audit order",
};

export const FIELDS: Record<string, string> = {
  einkuenfte_nsa: "Employment income",
  einkuenfte_gewerbe: "Business income",
  einkuenfte_vuv: "Rental income",
  summe_einkuenfte: "Total income",
  sonderausgaben: "Special expenses",
  agb: "Extraordinary burdens",
  zve: "Taxable income",
  est: "Income tax",
  soli: "Solidarity surcharge",
  kist: "Church tax",
  lst_est: "Wage tax withheld",
  vz_est: "Prepayments",
  rest_est: "Income tax due",
  lst_soli: "Surcharge withheld",
  rest_soli: "Surcharge due",
  lst_kist: "Church tax withheld",
  rest_kist: "Church tax due",
  zinsen_est: "Interest",
  einkommen: "Taxable income",
  kst: "Corporate tax",
  vz_kst: "Prepayments",
  rest_kst: "Corporate tax due",
  zinsen_kst: "Interest",
  umsatz_19: "Turnover at 19 %",
  umsatz_7: "Turnover at 7 %",
  ust: "VAT",
  vorsteuer: "Input VAT",
  zahllast: "VAT payable",
  vz_ust: "Advance returns",
  rest_ust: "VAT due",
  zinsen_ust: "Interest",
  gewinn: "Profit",
  hinzurechnungen: "Add-backs",
  kuerzungen: "Reductions",
  gewerbeertrag: "Trade income",
  freibetrag: "Allowance",
  messbetrag: "Base amount",
  hebesatz: "Multiplier",
  gewst: "Trade tax",
  vz_gewst: "Prepayments",
  rest_gewst: "Balance",
  vz_quartal: "Per quarter",
};
