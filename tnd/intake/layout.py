"""The layout reader: values from any layout, by what each amount is labelled with.

The label reader in `parse.py` knows the wording the desk has seen. Towns and offices print the same figures in
many other ways: taxes side by side in a column table, a pipe table, dot leaders, a sentence ("auf der Grundlage
des Steuermessbetrags von 3.983,00 € …"), "EUR 1 234,56" or "1234,56". This reader finds every amount, works out
its label (the text before it on its line or in its sentence) and the column it stands in, and maps
(role, column) or the label itself to a field with `config/extraction.yaml: layout`.

It proposes values only. They are trusted only if the notice's own arithmetic holds with them (`parse.verify`);
where a field has several candidates, the arithmetic chooses among them.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from typing import Any

from .. import config

AMOUNT = re.compile(
    r"(?<![\d.,/])(?:EUR\s?)?(?P<neg>-\s?)?(?P<whole>\d{1,3}(?:\.\d{3})+|\d{1,3}(?:[  ]\d{3})+|\d+),"
    r"(?P<cents>\d{2})(?![\d,])(?:\s?(?:€|EUR|Euro\b))?(?P<trail>-(?!\d))?"
)
WHOLE_EUROS = re.compile(r"(?<![\d.,/])(?P<whole>\d{1,3}(?:\.\d{3})+|\d+)(?![\d,])\s?(?:€|EUR|Euro\b)")  # "42.740 €"
GROUPED_EUROS = re.compile(r"(?<![\d.,/])(?P<whole>\d{1,3}(?:\.\d{3})+)(?![\d,.])(?P<trail>-(?!\d))?")  # "99.650"
# Amounts that cannot be negative: a minus sign printed with them only says "deducted"
NON_NEGATIVE = {
    "lst_est",
    "lst_soli",
    "lst_kist",
    "vz_est",
    "vz_soli",
    "vz_kist",
    "vz_kst",
    "vz_ust",
    "vz_gewst",
    "sonderausgaben",
    "agb",
    "vorsteuer",
    "freibetrag",
    "kuerzungen",
    "hinzurechnungen",
    "messbetrag",
    "hebesatz",
    "gewst",
    "est",
    "kst",
    "soli",
    "kist",
    "ust",
    "umsatz_19",
    "umsatz_7",
    "gewerbeertrag",
    "zve",
    "einkommen",
    "vz_quartal",
}
PERCENT = re.compile(r"(?<![\d.,])(?P<pct>\d{3})(?:,\d{1,2})?\s*(?:%|v\.\s?H\.|vom Hundert)")
DATE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")
ABBREV = {"lt", "abs", "nr", "v", "h", "vgl", "bzw", "ggf", "gem", "str", "z", "b", "st", "u", "a", "ca", "s"}


@dataclass
class Token:
    start: int
    end: int
    value: int
    percent: bool


def _tokens(line: str) -> list[Token]:
    clean = DATE.sub(lambda m: " " * len(m.group(0)), line)
    out = [Token(m.start(), m.end(), int(m["pct"]) * 100, True) for m in PERCENT.finditer(clean)]
    for m in AMOUNT.finditer(clean):
        if any(t.start <= m.start() < t.end for t in out):
            continue
        v = int(re.sub(r"[.\s ]", "", m["whole"])) * 100 + int(m["cents"])
        out.append(Token(m.start(), m.end(), -v if (m["neg"] or m["trail"]) else v, False))
    for m in WHOLE_EUROS.finditer(clean):
        if not any(t.start <= m.start() < t.end or m.start() <= t.start < m.end() for t in out):
            out.append(Token(m.start(), m.end(), int(m["whole"].replace(".", "")) * 100, False))
    for m in GROUPED_EUROS.finditer(clean):
        if not any(t.start <= m.start() < t.end or m.start() <= t.start < m.end() for t in out):
            v = int(m["whole"].replace(".", "")) * 100
            out.append(Token(m.start(), m.end(), -v if m["trail"] else v, False))
    return sorted(out, key=lambda t: t.start)


def _words(s: str) -> str:
    return " " + re.sub(r"[^\wäöüß§%]+", " ", s.lower()).strip() + " "


def _match(label: str, phrase: str) -> bool:
    """The phrase starts at a word boundary in the label (it may end inside a word: festgesetzt/festgesetzte)."""
    return (" " + _words(phrase).strip()) in _words(label)


def _best(label: str, table: dict[str, str]) -> tuple[int, str | None]:
    best: tuple[int, str | None] = (0, None)
    for phrase, target in table.items():
        if len(phrase) > best[0] and _match(label, phrase):
            best = (len(phrase), target)
    return best


def _sentence_tail(s: str) -> str:
    """The text after the last sentence boundary (not an abbreviation such as "lt." or "Abs.")."""
    cut = 0
    for m in re.finditer(r"([A-Za-zÄÖÜäöüß\d)]+)[.;:!?]\s+(?=\S)", s):
        if m.group(1).lower() not in ABBREV:
            cut = m.end()
    return s[cut:]


def _strip(label: str) -> str:
    return re.sub(r"[.…]{2,}|[|=×x*/\-–—+:]+(?=\s|$)|^\s*[=./–\-+×x]+", " ", label).strip(" ,;()|\t")


@dataclass
class Header:
    cols: list[tuple[int, int, str]]  # (start, end, column) in the order printed


class Layout:
    def __init__(self, kind: str) -> None:
        cfg = config.load("extraction")["layout"]
        self.kind = kind
        self.columns: dict[str, str] = {p: c for c, ps in cfg["columns"].items() for p in ps}
        self.roles: dict[str, str] = {p: r for r, ps in cfg["roles"].items() for p in ps}
        self.fields: dict[str, str] = cfg["fields"].get(kind, {})
        lines = dict(cfg["lines"].get(kind, {}))
        z = {"est": "zinsen_est", "kst": "zinsen_kst", "ust": "zinsen_ust"}.get(kind)
        if z:
            lines.update({p: z for p in cfg["lines"]["any"]})
        self.lines: dict[str, str] = lines
        self.suffix_rest: list[str] = cfg["suffix_rest"]
        self.zero: list[str] = cfg["zero_if_absent"].get(kind, [])
        own = {"gewst": {"messbetrag", "hebesatz", "gewst"}}.get(kind, set())
        # columns that are fields of their own (a town's table: Messbetrag | Hebesatz | Gewerbesteuer)
        self.field_columns = own
        tax_cols = {"est": {"est", "soli", "kist"}, "kst": {"kst", "soli"}, "vz_est": {"est", "soli", "kist"}}
        self.tax_columns: set[str] = tax_cols.get(kind, set()) | own

    def _header(self, line: str) -> Header | None:
        found: list[tuple[int, int, str]] = []
        low = line.lower()
        for phrase, col in sorted(self.columns.items(), key=lambda kv: -len(kv[0])):
            if col not in self.tax_columns:
                continue
            for m in re.finditer(r"(?<![\wäöüß])" + re.escape(phrase.lower()), low):
                if not any(s <= m.start() < e for s, e, _ in found):
                    found.append((m.start(), m.end(), col))
        found.sort()
        dedup: list[tuple[int, int, str]] = []
        for f in found:
            if not any(f[2] == d[2] for d in dedup):
                dedup.append(f)
        return Header(dedup) if dedup else None

    def _column_in(self, label: str) -> str | None:
        n, col = _best(label, {p: c for p, c in self.columns.items() if c in self.tax_columns})
        return col

    def _field(self, label: str, column: str | None, suffix: str, percent: bool) -> tuple[str | None, bool]:
        """(field, is_refund) for an amount with this label in this column."""
        lab = _strip(_sentence_tail(label))
        nl, line_field = _best(lab, self.lines)
        nr, role = _best(lab, self.roles)
        col_here = self._column_in(lab)
        if col_here in self.field_columns and role in (None, "tax"):
            return (col_here if (col_here == "hebesatz") == percent else None), False
        if line_field and nl >= nr:
            return line_field, False
        if percent:
            return ("hebesatz" if col_here == "hebesatz" or column == "hebesatz" else None), False
        if not role:
            if col_here and col_here not in self.field_columns:
                role, column = "tax", col_here
            elif column in self.field_columns and not re.search(r"[A-Za-zÄÖÜäöüß]", lab):
                return column, False
            elif "=" in label[-6:] and not lab:
                role = "tax"
            elif any(s in suffix.lower() for s in self.suffix_rest):
                role = "rest"
            else:
                return None, False
        refund = role == "refund"
        role = "rest" if refund else role
        col = col_here if col_here and col_here not in self.field_columns else column
        f = self.fields.get(f"{role}.{col or '-'}") or self.fields.get(f"{role}.-")
        return f, refund

    def candidates(self, text: str) -> dict[str, list[int]]:
        cands: dict[str, list[int]] = {}

        def add(f: str | None, v: int) -> None:
            if f in NON_NEGATIVE:
                v = abs(v)
            if f and v not in cands.setdefault(f, []):
                cands[f].append(v)

        table: Header | None = None
        context: str | None = None
        prev_tail = ""
        for raw in text.splitlines():
            line = raw.replace("|", " ")
            toks = _tokens(line)
            if not line.strip():
                table, prev_tail = None, ""
                continue
            if re.fullmatch(r"[\s\-=_+:]+", line):  # a table's rule line
                continue
            if not toks:
                h = self._header(line)
                if h and len(h.cols) >= 2:
                    table = h
                elif h and len(h.cols) == 1 and len(line.strip()) < 60:
                    table, context = None, h.cols[0][2]
                else:
                    table = None
                prev_tail = _sentence_tail(prev_tail + " " + line.strip())
                continue
            label0 = line[: toks[0].start]
            if table and len(toks) >= 2:
                is_quarter = bool(DATE.search(label0))
                cols = [c for _, _, c in table.cols]
                if len(toks) == len(cols):
                    pairs = list(zip(cols, toks, strict=True))
                else:  # fewer amounts than columns: the column whose header ends nearest the amount
                    pairs = [(min(table.cols, key=lambda c: abs(c[1] - t.end))[2], t) for t in toks]
                for col, t in pairs:
                    if is_quarter:
                        add(self.fields.get(f"quarter.{col}"), t.value)
                        continue
                    f, refund = self._field(label0, col, "", t.percent)
                    add(f, -abs(t.value) if refund else t.value)
                continue
            if table and len(toks) == 1 and not _strip(label0):
                table = None
            last = 0
            line_col = context  # "Kirchensteuer festgesetzt: …, anzurechnen: …, verbleibend: …" stays in its column
            for k, t in enumerate(toks):
                label = line[last : t.start]
                if k == 0 and not re.search(r"[A-Za-zÄÖÜäöüß]", _strip(label)):
                    label = prev_tail + " " + label
                named = self._column_in(_strip(_sentence_tail(label)))
                if k == 0 and named and named not in self.field_columns:
                    line_col = named
                suffix = line[t.end : toks[k + 1].start if k + 1 < len(toks) else len(line)]
                bare = _strip(DATE.sub(" ", label))
                if k == 0 and DATE.search(label) and not re.search(r"[A-Za-zÄÖÜäöüß]", bare):
                    add(self.fields.get(f"quarter.{line_col}"), t.value)  # a due date and its amount
                    last = t.end
                    continue
                f, refund = self._field(label, line_col, suffix, t.percent)
                add(f, -abs(t.value) if refund else t.value)
                last = t.end
            prev_tail = _sentence_tail(line[toks[-1].end :])
        low = re.sub(r"\s+", " ", text.lower())
        none_paid = r"(keine vorauszahlungen|vorauszahlungen [^.;]{0,40}nicht festgesetzt)"
        if self.kind == "gewst" and re.search(none_paid, low):
            cands.setdefault("vz_gewst", []).insert(0, 0)
        return cands


def read(kind: str, text: str, specs: dict[str, dict[str, Any]], verify: Any, make: Any) -> tuple[Any, Any]:
    """(a Parsed whose arithmetic holds, or None; the first complete reading, verified or not, or None).

    `make(fields)` builds a Parsed with these fields; `verify(p)` checks it (setting p.verified).
    """
    lay = Layout(kind)
    cands = {k: v for k, v in lay.candidates(text).items() if k in specs}
    required = [k for k, sp in specs.items() if not sp.get("optional") and k not in lay.zero and k not in cands]
    if kind == "est" and "summe_einkuenfte" in required:
        required.remove("summe_einkuenfte")
    if required:
        return None, None
    keys = list(cands)
    first = None
    options = [cands[k][:3] for k in keys]
    for n, combo in enumerate(itertools.product(*options)):
        if n >= 64:
            break
        fields = dict(zip(keys, combo, strict=True))
        for z in lay.zero:
            if z in specs:
                fields.setdefault(z, 0)
        if kind == "est" and "summe_einkuenfte" not in fields:
            incomes = ("einkuenfte_nsa", "einkuenfte_gewerbe", "einkuenfte_vuv")
            fields["summe_einkuenfte"] = sum(fields.get(k, 0) for k in incomes)
        p = make(fields)
        verify(p)
        if p.verified:
            return p, p
        first = first or p
    return None, first
