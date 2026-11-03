"""Who has to act on a notice, and how urgently. Rules decide; the model only explains (tnd/drafts).

Actions:
  close               the notice matches the filed return and every check passed; recorded, nobody needs to act
  inform_client       nothing to object to, but the client should hear about it (a refund, a change in their favour,
                      new prepayments)
  objection_review    the office deviated against the client by more than the materiality threshold: an advisor
                      decides whether to object; a draft is prepared
  objection_required  the notice is wrong on its face (a town's arithmetic or Hebesatz, a stale Messbetrag, interest,
                      an estimate because no return was filed): object, or file the return, before the deadline
  task                a letter asks for something by a date (documents, a missing return, an audit)
  duplicate           a copy of a notice already on the desk
  misrouted           no firm in the group knows the tax number
  review              the desk could not read or match the notice with certainty; a person looks first
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import config
from .checks import Finding

ERRORS = {"wrong_hebesatz", "stale_messbetrag", "arithmetic", "interest", "estimate", "no_return"}


@dataclass
class Decision:
    action: str
    reasons: list[str] = field(default_factory=list)
    blocked_close: list[str] = field(default_factory=list)


def decide(kind: str | None, verified: bool, matched: bool, duplicate_of: str | None, findings: list[Finding],
           tax_effect: int, estimate: bool, has_filed: bool) -> Decision:
    cfg = config.load("rules")["decide"]
    if duplicate_of:
        return Decision("duplicate", [f"same notice as {duplicate_of}"])
    if not matched:
        return Decision("misrouted", ["no client in the group has this tax number"])
    if kind is None:
        return Decision("review", ["kind of notice not recognised"])
    if kind in cfg["task_kinds"]:
        return Decision("task", [f"{kind}: the authority expects something by a date"])
    if not verified:
        return Decision("review", ["values could not be confirmed by the notice's own arithmetic"])
    errors = [f for f in findings if f.type in ERRORS]
    if estimate or errors:
        return Decision("objection_required", [f.detail or f.type for f in errors] or ["estimated assessment"])
    if kind == "vz_est":
        return Decision("inform_client", ["new prepayments"])
    if kind != "gewst" and not has_filed:
        return Decision("review", ["no filed return on record to compare with"])
    devs = [f for f in findings if f.type == "deviation"]
    if not devs:
        return Decision("close", ["matches the filed return; arithmetic and interest checked"])
    against = [f for f in devs if f.against and f.primary]
    if against and (kind == "gewst_mess" or tax_effect >= cfg["objection_materiality_cents"]):
        return Decision("objection_review", [f"{len(against)} change(s) against the client; tax effect "
                                             f"{tax_effect / 100:.2f} €"], ["deviation"])
    return Decision("inform_client", ["deviations in the client's favour or below the threshold"], ["deviation"])
