"""
Score invoice matches against a synthetic answer key.

Scoring rules, fixed before looking at any results:

* **Component accuracy** is the headline. An invoice is correct when the predicted component is the
  true (primary) component, or when both say routine with no component. ``unsure`` counts as not
  correct. Denominator: all invoices. A memo naming the wrong building is still scored against the
  true component. A two-component invoice is scored on its primary component.
* **Coverage** is the share of invoices the method decided (not ``unsure``).
* **Precision** is component accuracy over decided invoices only.
* **Dollar-weighted accuracy** weights each invoice by its amount, since replacement projects are
  few but carry most of the money.
* **Work type** (routine, repair, replacement) is reported but is not a headline: once the component
  is right, the amount-over-cost rule separates repairs from replacements almost by construction.
* **Wrong-fund flags** are scored against the truth: a flag is right when the true fund differs
  from the fund the invoice was booked to.

All numbers are on synthetic data, and the rules and the generator have the same author.
"""

from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from app.domain.matching import MatchResult

LABELS = ("routine", "repair", "replacement", "unsure")


class InvoiceAmount(Protocol):
    id: str
    amount: float
    fund_booked: str


def _ratio(a: float, b: float) -> float:
    return round(a / b, 4) if b else 0.0


def score_matches(results: Sequence[MatchResult], invoices: Sequence[InvoiceAmount], truths: dict[str, dict]) -> dict:
    """``truths`` is the answer key's ``invoices`` mapping (invoice id -> truth dict)."""
    amounts = {i.id: i.amount for i in invoices}
    booked = {i.id: i.fund_booked for i in invoices}
    n = len(results)
    total_dollars = sum(amounts[r.invoice_id] for r in results)
    correct = decided = 0
    correct_dollars = 0.0
    work_correct = 0
    confusion: Counter[tuple[str, str]] = Counter()
    by_truth: dict[str, Counter[str]] = {}
    ambiguous = Counter()
    flag_tp = flag_fp = 0
    wrong_fund_truth = 0

    for r in results:
        t = truths[r.invoice_id]
        truth_label = t["work_type"]
        confusion[(truth_label, r.label)] += 1
        bucket = by_truth.setdefault(truth_label, Counter())
        bucket["n"] += 1
        is_decided = r.label != "unsure"
        decided += is_decided
        ok = is_decided and (
            (truth_label == "routine" and r.label == "routine")
            or (t["component_id"] is not None and r.component_id == t["component_id"])
        )
        correct += ok
        bucket["correct"] += ok
        bucket["unsure"] += not is_decided
        if ok:
            correct_dollars += amounts[r.invoice_id]
        work_correct += r.label == truth_label
        if t.get("ambiguous"):
            ambiguous["n"] += 1
            ambiguous["component_correct"] += ok
            ambiguous["labelled_repair"] += r.label == "repair"
            ambiguous["flagged_wording"] += "wording_says_replacement" in r.flags
        is_wrong_fund = t["fund"] != booked[r.invoice_id]
        wrong_fund_truth += is_wrong_fund
        if "booked_to_wrong_fund" in r.flags:
            if is_wrong_fund:
                flag_tp += 1
            else:
                flag_fp += 1

    return {
        "label": "SYNTHETIC data; rules and generator share an author, so treat as optimistic",
        "invoices": n,
        "coverage": _ratio(decided, n),
        "component_accuracy": _ratio(correct, n),
        "precision_on_decided": _ratio(correct, decided),
        "dollar_weighted_accuracy": _ratio(correct_dollars, total_dollars),
        "work_type_accuracy": _ratio(work_correct, n),
        "by_true_type": {
            k: {
                "n": v["n"],
                "accuracy": _ratio(v["correct"], v["n"]),
                "unsure": _ratio(v["unsure"], v["n"]),
            }
            for k, v in sorted(by_truth.items())
        },
        "confusion_true_by_predicted": {
            truth: {pred: confusion[(truth, pred)] for pred in LABELS} for truth in LABELS[:3]
        },
        "ambiguous": dict(ambiguous),
        "wrong_fund_flags": {
            "true_wrong_fund_invoices": wrong_fund_truth,
            "flagged_correctly": flag_tp,
            "flagged_wrongly": flag_fp,
            "recall": _ratio(flag_tp, wrong_fund_truth),
        },
    }
