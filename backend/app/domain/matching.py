"""
Rule-based invoice matching: decide, for each vendor invoice, whether it is routine upkeep, a repair
to a reserve component, or part of a component's replacement, and which component.

Inputs are only what a client hands over: the invoices (vendor, date, amount, memo), the reserve
study (component names, categories, locations, costs) and the association's inflation rate. The
fund an invoice was *booked* to is deliberately not an input; it's compared afterwards to flag
spend booked to the wrong fund.

How a decision is made, in order:

1. **Contract links.** "Balance due - contract 4471", "Final invoice #4471", "Retainage release
   4471" and "Progress billing #1 contract 4471" belong to the project whose deposit memo names
   contract 4471 in the same association, so they inherit its component and are replacements.
2. **Component evidence.** Words from each component's own name, plus a short generic lexicon of
   maintenance terms (``LEXICON``), are looked for in the memo. The vendor's trade (read from words
   in its name, ``VENDOR_TRADES``) and a building named in the memo narrow the candidates.
3. **Routine.** No component evidence, and either a routine-only trade (cleaning, pest, snow,
   hauling, grounds) or routine wording, means routine upkeep.
4. **Work type.** Amount over the component's replacement cost, inflated to the invoice year:
   at or above ``CAPITAL_THRESHOLD`` it's a replacement, below it a repair. Replacement wording on
   an invoice under the threshold adds a ``wording_says_replacement`` flag for review.
5. **Unsure.** Anything without a single clear best candidate. These go to the AI step.

This module never imports app.synth: the rules must not see how the data was generated.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

CAPITAL_THRESHOLD = 0.15  # share of replacement cost at which work counts as capital (reserve) spend

# Trade words in vendor names. Generic, not tied to any vendor list.
VENDOR_TRADES: tuple[tuple[str, str], ...] = (
    (r"roof", "roofing"),
    (r"gutter", "roofing"),
    (r"elevator|\blift\b", "elevator"),
    (r"mech|hvac|heating|\bair\b|cooling", "hvac"),
    (r"plumb|plbg|pipe", "plumbing"),
    (r"mason|brick|restoration", "masonry"),
    (r"paint", "painting"),
    (r"electric|\belec\b|alarm", "electrical"),
    (r"paving|asphalt|sealcoat", "paving"),
    (r"siding|exteriors", "siding"),
    (r"carpent|deck|fenc", "carpentry"),
    (r"\bpools?\b", "pool"),
    (r"landscap|lndscp|grounds|lawn", "landscape"),
    (r"clean|janitor|spotless|custodial", "janitorial"),
    (r"pest|termite", "pest"),
    (r"snow|plow", "snow"),
    (r"haul|waste|trash|disposal", "waste"),
)
ROUTINE_TRADES = {"janitorial", "pest", "snow", "waste"}

# Which trades work on a component, read from its category and name.
COMPONENT_TRADES: tuple[tuple[str, set[str]], ...] = (
    (r"roof|gutter|downspout", {"roofing"}),
    (r"elevator", {"elevator"}),
    (r"boiler|hvac|heating|cooling", {"hvac", "plumbing"}),
    (r"water heater|plumbing|piping", {"plumbing"}),
    (r"masonry|facade|brick", {"masonry"}),
    (r"paint|carpet|hallway", {"painting"}),
    (r"fire alarm|lighting|electrical", {"electrical"}),
    (r"paving|roads|sealcoat|garage|asphalt", {"paving"}),
    (r"siding", {"siding"}),
    (r"deck|balcon|fenc|playground", {"carpentry"}),
    (r"pool", {"pool"}),
    (r"pond|landscap", {"landscape"}),
)

# Generic maintenance vocabulary: a memo term -> the component-name word it points to.
LEXICON: dict[str, str] = {
    "shingle": "roof",
    "flashing": "roof",
    "epdm": "membrane",
    "leak": "",  # too generic to point anywhere on its own
    "brick": "masonry",
    "repoint": "masonry",
    "mortar": "masonry",
    "no heat": "boiler",
    "burner": "boiler",
    "hot water": "water heaters",
    "smoke detector": "fire alarm",
    "pothole": "paving",
    "repave": "paving",
    "repaving": "paving",
    "overlay": "paving",
    "asphalt": "paving",
    "striping": "sealcoat",
    "restripe": "sealcoat",
    "railing": "decks",
    "balcony": "balconies",
    "downspout": "downspouts",
    "light": "lighting",
    "led": "lighting",
    "cooling": "hvac",
    "a/c": "hvac",
    "rooftop unit": "hvac",
    "pump": "pumps",
    "filter": "filters",
    "plaster": "pool",
    "dredging": "pond",
    "outfall": "pond",
    "erosion": "pond",
    "algae": "pond",
    "stormwater": "pond",
    "retention basin": "pond",
    "gate": "fencing",
    "fence": "fencing",
    "play structure": "playground",
    "corridor": "hallway",
    "carpet": "carpet",
    "trim": "trim",
}
ROUTINE_WORDS = re.compile(
    r"\b(grounds maintenance|landscape contract|mowing|trimming|cleaning|janitorial|pest|snow|plow|salting"
    r"|trash|dumpster|hauling)\b",
    re.I,
)
REPLACEMENT_WORDS = re.compile(
    r"\b(replace|replacement|new|tear-off|modernization|resurfacing|repaving|overlay|restoration|renovation"
    r"|repointing|dredging|install|installation|phase \d)\b",
    re.I,
)
_CONTRACT_DEPOSIT = re.compile(r"\bdeposit\b.*\bcontract\s+(\d{3,6})\b", re.I)
_CONTRACT_FOLLOWUP = re.compile(
    r"\b(?:balance due\s*-\s*contract|contract|final invoice\s*#|retainage release)\s*(\d{3,6})\b", re.I
)
_BUILDING = re.compile(r"\b(?:bldg\.?|building)\s+([A-Z])\b", re.I)
_STOP = {"and", "of", "the", "mill", "plant", "devices", "equipment", "panel", "poles"}


class InvoiceLike(Protocol):
    id: str
    association_id: str
    vendor_name: str
    invoice_date: date
    amount: float
    memo: str
    fund_booked: str


class ComponentLike(Protocol):
    id: str
    association_id: str
    category: str
    name: str
    location: str | None
    replacement_cost: float


class AssociationLike(Protocol):
    id: str
    study_year: int
    inflation_rate: float


@dataclass
class MatchResult:
    invoice_id: str
    label: str  # routine | repair | replacement | unsure
    component_id: str | None
    confidence: float  # 0..1, how sure the rules are about label and component together
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)  # e.g. booked_to_wrong_fund, wording_says_replacement
    method: str = "rules"


@dataclass
class _Candidate:
    component: ComponentLike
    words: set[str]  # name words a memo can mention
    trades: set[str]


def vendor_trade(vendor_name: str) -> str | None:
    name = vendor_name.lower()
    for pattern, trade in VENDOR_TRADES:
        if re.search(pattern, name):
            return trade
    return None


def _stem(word: str) -> str:
    for suffix in ("ies", "es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 3:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def component_words(component: ComponentLike) -> set[str]:
    """Words of a component's name (and category) that a memo might use, stemmed."""
    text = re.sub(r"[()]", " ", f"{component.name} {component.category.replace('_', ' ')}").lower()
    return {_stem(w) for w in re.findall(r"[a-z]+", text) if len(w) > 2 and w not in _STOP}


def component_trades(component: ComponentLike) -> set[str]:
    text = f"{component.name} {component.category}".lower()
    trades: set[str] = set()
    for pattern, ts in COMPONENT_TRADES:
        if re.search(pattern, text):
            trades |= ts
    return trades


def memo_building(memo: str) -> str | None:
    m = _BUILDING.search(memo)
    return f"Bldg {m.group(1).upper()}" if m else None


def memo_terms(memo: str) -> set[str]:
    """Stemmed memo words plus the component words that lexicon phrases point to."""
    low = memo.lower()
    terms = {_stem(w) for w in re.findall(r"[a-z]+", low) if len(w) > 2}
    for phrase, target in LEXICON.items():
        if target and re.search(rf"\b{re.escape(phrase)}(?:s|es)?\b", low):
            terms |= {_stem(w) for w in target.split()}
    return terms


def inflated_cost(component: ComponentLike, assoc: AssociationLike, year: int) -> float:
    return component.replacement_cost * (1 + assoc.inflation_rate) ** (year - assoc.study_year)


def _hits(words: set[str], terms: set[str]) -> set[str]:
    """Component words the memo uses, allowing a longer memo word (sealcoat -> sealcoating)."""
    return {w for w in words if w in terms or (len(w) >= 5 and any(t.startswith(w) for t in terms))}


def _score(c: _Candidate, terms: set[str], trade: str | None, building: str | None) -> float:
    score = 2.0 * len(_hits(c.words, terms))
    if trade and trade in c.trades:
        score += 1.5
    elif trade and c.trades and trade not in c.trades and trade not in ROUTINE_TRADES:
        score -= 2.0
    if building and c.component.location:
        score += 1.0 if c.component.location == building else -1.0
    return score


def match_invoices(
    invoices: Sequence[InvoiceLike],
    components: Iterable[ComponentLike],
    associations: Iterable[AssociationLike],
) -> list[MatchResult]:
    """Match every invoice. Pure: no database, no clock, no randomness; same inputs, same output."""
    assocs = {a.id: a for a in associations}
    by_assoc: dict[str, list[_Candidate]] = {}
    for comp in sorted(components, key=lambda c: c.id):  # input order must not matter
        by_assoc.setdefault(comp.association_id, []).append(
            _Candidate(comp, component_words(comp), component_trades(comp))
        )

    results: dict[str, MatchResult] = {}
    deposits: dict[tuple[str, str], str] = {}  # (association, contract) -> deposit invoice id
    followups: list[tuple[InvoiceLike, str]] = []

    for inv in sorted(invoices, key=lambda i: (i.invoice_date, i.id)):
        dep = _CONTRACT_DEPOSIT.search(inv.memo)
        follow = None if dep else _CONTRACT_FOLLOWUP.search(inv.memo)
        if follow:
            followups.append((inv, follow.group(1)))
            continue
        result = _match_one(inv, by_assoc.get(inv.association_id, []), assocs[inv.association_id])
        if dep:
            deposits[(inv.association_id, dep.group(1))] = inv.id
            if result.label in ("repair", "replacement"):
                result.label = "replacement"
                result.reasons.append(f"deposit on contract {dep.group(1)}")
        results[inv.id] = result

    for inv, contract in followups:
        dep_id = deposits.get((inv.association_id, contract))
        parent = results.get(dep_id) if dep_id else None
        if parent and parent.component_id:
            results[inv.id] = MatchResult(
                inv.id,
                "replacement",
                parent.component_id,
                min(parent.confidence, 0.95),
                [f"contract {contract} links to deposit {dep_id}"],
            )
        else:
            results[inv.id] = MatchResult(
                inv.id, "unsure", None, 0.0, [f"contract {contract} has no matched deposit in this association"]
            )

    by_id = {i.id: i for i in invoices}
    for r in results.values():
        fund_flag(r, by_id[r.invoice_id])
    return [results[i.id] for i in invoices]


def _match_one(inv: InvoiceLike, candidates: list[_Candidate], assoc: AssociationLike) -> MatchResult:
    trade = vendor_trade(inv.vendor_name)
    terms = memo_terms(inv.memo)
    building = memo_building(inv.memo)
    reasons = [f"vendor trade: {trade or 'unknown'}"]
    if building:
        reasons.append(f"memo names {building}")

    scored = sorted(((_score(c, terms, trade, building), c) for c in candidates), key=lambda x: -x[0])
    evidence = [(s, c) for s, c in scored if _hits(c.words, terms)]
    if not evidence:
        # No component named. Routine if the vendor or wording says so.
        if trade in ROUTINE_TRADES or ROUTINE_WORDS.search(inv.memo):
            return MatchResult(inv.id, "routine", None, 0.9, [*reasons, "routine trade or wording, no component named"])
        # A component trade with only one possible component (after the building filter) is still a match.
        fits = [c for s, c in scored if trade and trade in c.trades and s > 0]
        if len(fits) == 1:
            return with_work_type(
                inv, fits[0].component, assoc, 0.6, [*reasons, "only component this trade works on here"]
            )
        return MatchResult(inv.id, "unsure", None, 0.0, [*reasons, "no component named and no single fit"])

    best_score, best = evidence[0]
    runner_up = evidence[1][0] if len(evidence) > 1 else None
    if best_score <= 0 or (runner_up is not None and runner_up >= best_score):
        tied = ", ".join(c.component.id for s, c in evidence if s == best_score)
        return MatchResult(inv.id, "unsure", None, 0.0, [*reasons, f"no single best component ({tied})"])
    margin = best_score - (runner_up or 0.0)
    confidence = min(0.5 + 0.1 * margin, 0.95)
    hit = ", ".join(sorted(_hits(best.words, terms)))
    return with_work_type(inv, best.component, assoc, confidence, [*reasons, f"memo mentions {hit}"])


def with_work_type(
    inv: InvoiceLike, component: ComponentLike, assoc: AssociationLike, confidence: float, reasons: list[str]
) -> MatchResult:
    """Repair or replacement by the capital threshold, for an invoice already tied to ``component``."""
    share = inv.amount / inflated_cost(component, assoc, inv.invoice_date.year)
    label = "replacement" if share >= CAPITAL_THRESHOLD else "repair"
    reasons = [*reasons, f"{share:.0%} of replacement cost"]
    flags = []
    if label == "repair" and REPLACEMENT_WORDS.search(inv.memo):
        flags.append("wording_says_replacement")
    return MatchResult(inv.id, label, component.id, round(confidence, 2), reasons, flags)


def fund_flag(result: MatchResult, inv: InvoiceLike) -> None:
    """Compare the booked fund with what the label implies (only for decided invoices)."""
    if result.label == "unsure":
        return
    expected = "reserve" if result.label == "replacement" else "operating"
    if inv.fund_booked != expected:
        result.flags.append("booked_to_wrong_fund")
