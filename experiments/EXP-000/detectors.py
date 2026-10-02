"""Pure detectors for EXP-000's scrubber. No I/O, no state, no network.

Each finder returns `Span`s over the given text. `resolve` drops overlaps by category priority,
and `redactions` applies the amount rule: **a bare amount is never redacted**, because EXP-000's
own labels turn on phrases like "around 40" and "might stretch to 45". An amount is redacted only
when it sits within `amount_window` characters of an account identifier, which is the
"amount with account info" case.

Known limits, stated here because the README promises them:
- ADDRESS defaults to pincodes and premise numbers only. Localities and roads are left alone,
  because in a property conversation they are the state being tracked. The blunt
  locality-clause rule is opt-in and every one of its hits is logged.
- PERSON is roster-only. A third party named in passing is not detected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Iterable, Sequence

#: Higher wins when two spans overlap.
PRIORITY = {
    "EMAIL": 90, "UPI": 85, "IFSC": 80, "CARD": 75, "ACCOUNT": 70,
    "TXNREF": 65, "PHONE": 60, "PERSON": 50, "ADDRESS": 40, "AMOUNT": 10,
}

#: Categories replaced in the output. AMOUNT is detected but only conditionally redacted.
REDACTED = {"EMAIL", "UPI", "IFSC", "CARD", "ACCOUNT", "TXNREF", "PHONE", "PERSON", "ADDRESS"}

ACCOUNT_CATEGORIES = {"ACCOUNT", "IFSC", "CARD", "UPI", "TXNREF"}

AMOUNT_WINDOW = 60

_AT_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9.-]{2,}\b")
_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_DIGIT_RUN = re.compile(r"(?<!\d)\d[\d\s-]{7,24}\d(?!\d)")
_ACCOUNT_KEYWORD = re.compile(
    r"\b(a/?c|acct|account|accno|ifsc|neft|imps|rtgs|beneficiary)\b", re.I)
_TXNREF = re.compile(
    r"\b(?:utr|txn|transaction|ref|reference)\s*(?:id|no\.?|number|#)?\s*[:\-]?\s*"
    r"([A-Za-z0-9]{8,24})\b", re.I)
_PHONE_CANDIDATE = re.compile(r"(?<![\w])(\+?\d[\d\s-]{6,18}\d)(?![\w])")
_INDIAN_MOBILE = re.compile(r"(?:0|91)?[6-9]\d{9}")
_AMOUNT = re.compile(
    r"(?:(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?(?:\s*(?:lakhs?|lacs?|crores?|cr|k|thousand|mn))?"
    r"|[\d,]+(?:\.\d+)?\s*(?:lakhs?|lacs?|crores?|cr|k|thousand|mn)\b)", re.I)
_PINCODE = re.compile(r"(?<!\d)[1-9]\d{5}(?!\d)")
#: A premise keyword followed by a designator containing a digit: "Flat 402", "H.No 3-4-12",
#: "Plot 17", "Door No 5". Only the designator is redacted, so the property type survives:
#: "flat" and "plot" are state the benchmark tracks. The lookahead requires a digit, which is
#: what keeps "flat near Gachibowli" from matching.
_PREMISE = re.compile(
    r"(?<![-\w])(?:flat|apartment|apt|villa|plot|shop|unit|door|house|h\.?\s*no\.?|d\.?\s*no\.?)"
    r"\s*(?:no\.?|number|#|:)?\s*"
    r"((?=[\w/-]*\d)\w+(?:[-/]\w+)*)", re.I)
_ADDRESS_KEYWORD = re.compile(
    r"\b(flat|plot|door|house\s*no|h\.?no|road|rd|street|st|lane|nagar|colony|sector|block|"
    r"apartment|apt|tower|society|layout|cross|main|pincode|pin\s*code|landmark|opposite|opp)\b",
    re.I)
_CLAUSE_END = re.compile(r"[,.;\n]")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    category: str
    text: str
    #: For PERSON, the roster entry this surface form belongs to, so that "Priya" and
    #: "Priya Sharma" resolve to one placeholder. None for every other category.
    canonical: str | None = None


def _span(text: str, start: int, end: int, category: str) -> Span:
    return Span(start=start, end=end, category=category, text=text[start:end])


def luhn_ok(digits: str) -> bool:
    """Luhn checksum, used to keep ACCOUNT runs from being reported as card numbers."""
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def find_at_handles(text: str) -> list[Span]:
    """Split `local@domain` into EMAIL and UPI.

    A UPI virtual address has no dot in its handle (`name@okhdfcbank`); an email domain does
    (`name@example.com`). That is the only workable discriminator from text alone.
    """
    out = []
    for m in _AT_PATTERN.finditer(text):
        domain = m.group(0).split("@", 1)[1]
        out.append(_span(text, m.start(), m.end(), "EMAIL" if "." in domain else "UPI"))
    return out


def find_ifsc(text: str) -> list[Span]:
    return [_span(text, m.start(), m.end(), "IFSC") for m in _IFSC.finditer(text)]


def find_txn_refs(text: str) -> list[Span]:
    return [_span(text, m.start(1), m.end(1), "TXNREF") for m in _TXNREF.finditer(text)]


def looks_like_phone(digits: str, *, has_plus: bool = False) -> bool:
    """One predicate shared by the phone and account finders, so they cannot disagree.

    Without this, "+91 98765 43210" strips to twelve digits and lands in the account range,
    which would give the same person's number two different placeholders depending on how it
    was typed. A twelve-digit account number beginning 91 followed by 6-9 is read as a phone by
    this rule; both readings redact the value, only the category differs.
    """
    if _INDIAN_MOBILE.fullmatch(digits):
        return True
    return has_plus and 8 <= len(digits) <= 15


def find_digit_identifiers(text: str) -> list[Span]:
    """Card numbers, account numbers, and the digit runs that are neither.

    A run is a CARD when it is 13-19 digits and passes Luhn, an ACCOUNT when it is 11-18 digits
    or 9-18 with an account keyword nearby. Anything `looks_like_phone` accepts is left to the
    phone finder.
    """
    out = []
    for m in _DIGIT_RUN.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        has_plus = m.start() > 0 and text[m.start() - 1] == "+"
        if looks_like_phone(digits, has_plus=has_plus):
            continue
        near = text[max(0, m.start() - AMOUNT_WINDOW):m.end() + AMOUNT_WINDOW]
        keyword = bool(_ACCOUNT_KEYWORD.search(near))
        if 13 <= len(digits) <= 19 and luhn_ok(digits):
            out.append(_span(text, m.start(), m.end(), "CARD"))
        elif 11 <= len(digits) <= 18 or (9 <= len(digits) <= 18 and keyword):
            out.append(_span(text, m.start(), m.end(), "ACCOUNT"))
    return out


def find_phones(text: str) -> list[Span]:
    """Candidate digit runs validated by `looks_like_phone`, separators and all."""
    out = []
    for m in _PHONE_CANDIDATE.finditer(text):
        raw = m.group(1)
        digits = re.sub(r"\D", "", raw)
        if looks_like_phone(digits, has_plus=raw.startswith("+")):
            out.append(_span(text, m.start(1), m.end(1), "PHONE"))
    return out


def find_amounts(text: str) -> list[Span]:
    """Currency-marked or scale-worded amounts. Bare integers are deliberately not amounts."""
    return [_span(text, m.start(), m.end(), "AMOUNT") for m in _AMOUNT.finditer(text)]


def find_addresses(text: str, *, clauses: bool = False) -> list[Span]:
    """Pincodes and premise numbers by default; locality clauses only when asked.

    The default is deliberately narrow. In a property conversation a locality or a road is the
    state being tracked, not an identifier: "3BHK flat near Gachibowli" is a location preference
    and survives untouched, while the "402" in "Flat 402, Sai Residency" does not.

    `clauses` turns on the opt-in rule, which runs from a locality keyword (road, nagar, sector,
    landmark and the rest) to the next comma, semicolon, period or newline. It is the bluntest
    rule in this module, it will remove ordinary text, and every hit is written to the audit
    report so the operator can see exactly what went.
    """
    out = [_span(text, m.start(), m.end(), "ADDRESS") for m in _PINCODE.finditer(text)]
    out += [_span(text, m.start(1), m.end(1), "ADDRESS") for m in _PREMISE.finditer(text)]
    if clauses:
        for m in _ADDRESS_KEYWORD.finditer(text):
            end = _CLAUSE_END.search(text, m.end())
            out.append(_span(text, m.start(), end.start() if end else len(text), "ADDRESS"))
    return out


def find_names(text: str, roster: Sequence[str]) -> list[Span]:
    """Occurrences of known speaker names, longest first so full names beat first names.

    Each hit carries the roster entry it came from, so a first name and a full name collapse to
    one placeholder. Without that, "Thanks Priya" and "this is Priya Sharma" would be recorded
    as two different people.
    """
    out = []
    for name in sorted({n.strip() for n in roster if n and n.strip()}, key=len, reverse=True):
        for part in _name_variants(name):
            for m in re.finditer(rf"(?<!\w){re.escape(part)}(?!\w)", text, re.I):
                out.append(Span(start=m.start(), end=m.end(), category="PERSON",
                                text=text[m.start():m.end()], canonical=name))
    return out


def _name_variants(name: str) -> list[str]:
    """The full name and each of its word-like parts, longest first."""
    name = name.strip()
    parts = [p for p in re.split(r"\s+", name) if len(p) > 2]
    return sorted({name, *parts}, key=len, reverse=True)


def find_all(text: str, roster: Sequence[str] = (), *, address_clauses: bool = False) -> list[Span]:
    return (
        find_at_handles(text)
        + find_ifsc(text)
        + find_txn_refs(text)
        + find_digit_identifiers(text)
        + find_phones(text)
        + find_amounts(text)
        + find_addresses(text, clauses=address_clauses)
        + find_names(text, roster)
    )


def resolve(spans: Iterable[Span]) -> list[Span]:
    """Drop overlapping spans, keeping higher priority then longer, and return them in order."""
    ordered = sorted(spans, key=lambda s: (-PRIORITY[s.category], -(s.end - s.start), s.start))
    kept: list[Span] = []
    for span in ordered:
        if any(span.start < k.end and k.start < span.end for k in kept):
            continue
        kept.append(span)
    return sorted(kept, key=lambda s: s.start)


def redactions(spans: Sequence[Span], *, amount_window: int = AMOUNT_WINDOW) -> list[Span]:
    """The spans actually replaced: everything in REDACTED, plus account-adjacent amounts."""
    accounts = [s for s in spans if s.category in ACCOUNT_CATEGORIES]
    out = []
    for span in spans:
        if span.category in REDACTED:
            out.append(span)
        elif span.category == "AMOUNT" and any(
            abs(span.start - a.end) <= amount_window or abs(a.start - span.end) <= amount_window
            for a in accounts
        ):
            out.append(span)
    return sorted(out, key=lambda s: s.start)
