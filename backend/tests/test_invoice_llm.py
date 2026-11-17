"""Claude invoice matching, run on stub responses. No test calls the network or a paid API."""

import json
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.agents.invoice_llm import (
    POLICY,
    ResponseCache,
    build_request,
    match_unsure_with_llm,
)
from app.domain.matching import MatchResult


@dataclass
class Inv:
    id: str
    association_id: str
    vendor_name: str
    invoice_date: date
    amount: float
    memo: str
    fund_booked: str = "operating"


@dataclass
class Comp:
    id: str
    association_id: str
    category: str
    name: str
    location: str | None
    replacement_cost: float


@dataclass
class Assoc:
    id: str
    study_year: int = 2016
    inflation_rate: float = 0.0


COMPS = [
    Comp("G-DHW-B", "G", "plumbing", "Domestic water heaters", "Bldg B", 20_000),
    Comp("G-BOIL-B", "G", "mechanical", "Central boiler plant", "Bldg B", 60_000),
]
ASSOCS = [Assoc("G")]


def _inv(i: int, amount: float = 900.0, fund: str = "operating") -> Inv:
    return Inv(f"I{i}", "G", "Brandywine Plbg", date(2020, 3, i + 1), amount, "anode rod Bldg B", fund)


def _unsure(inv: Inv) -> MatchResult:
    return MatchResult(inv.id, "unsure", None, 0.0, ["no component named and no single fit"])


def _response(payload, stop_reason="end_turn"):
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(
            input_tokens=800, output_tokens=60, cache_read_input_tokens=0, cache_creation_input_tokens=0
        ),
        _request_id="req_stub",
    )


class Stub:
    """Transport that returns queued responses (or raises queued exceptions) and records requests."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, kwargs):
        self.requests.append(kwargs)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def _run(invoices, stub, cache=None, max_calls=10):
    return match_unsure_with_llm(
        invoices,
        COMPS,
        ASSOCS,
        [_unsure(i) for i in invoices],
        stub,
        cache or ResponseCache(None),
        model="claude-opus-5-5",
        max_calls=max_calls,
    )


def _answer(kind="component", ref="DHW-B", confidence="high", reason="anode rods are in water heaters"):
    return {"kind": kind, "component_ref": ref, "confidence": confidence, "reason": reason}


def test_a_good_answer_becomes_a_match_and_code_decides_the_work_type():
    small, big = _inv(0, amount=900), _inv(1, amount=9_000, fund="operating")
    matches, summary = _run([small, big], Stub(_response(_answer()), _response(_answer())))
    by_id = {m.invoice_id: m for m in matches}
    assert (by_id["I0"].label, by_id["I0"].component_id, by_id["I0"].method) == ("repair", "G-DHW-B", "llm")
    assert by_id["I1"].label == "replacement", "9,000 is 45% of the heaters' cost: code applies the 15% rule"
    assert "booked_to_wrong_fund" in by_id["I1"].flags
    assert by_id["I0"].confidence == 0.85 and by_id["I0"].reasons[0].startswith("claude (high)")
    assert summary.counts() == {"ok": 2}
    assert summary.tokens()["input"] == 1600


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (_response(_answer(ref="ROOF-Z")), "invalid"),
        (_response(_answer(kind="routine", ref="DHW-B")), "invalid"),
        (_response(_answer(kind="component", ref=None)), "invalid"),
        (_response("not json at all"), "invalid"),
        (_response({"kind": "component"}), "invalid"),
        (_response(_answer(), stop_reason="refusal"), "refused"),
        (_response(_answer(), stop_reason="max_tokens"), "truncated"),
        (_response(_answer(kind="unsure", ref=None)), "unsure"),
    ],
)
def test_unusable_answers_are_recorded_not_dropped(response, status):
    matches, summary = _run([_inv(0)], Stub(response))
    assert matches == []
    assert [a.status for a in summary.attempts] == [status]
    attempt = summary.attempts[0]
    assert attempt.raw_text is not None and attempt.request_id == "req_stub"
    if status not in ("unsure",):
        assert attempt.error


def test_routine_answer_without_a_component_is_used():
    matches, _ = _run([_inv(0)], Stub(_response(_answer(kind="routine", ref=None))))
    assert [(m.label, m.component_id) for m in matches] == [("routine", None)]


def test_budget_caps_live_calls_and_records_the_rest():
    invoices = [_inv(i) for i in range(3)]
    stub = Stub(_response(_answer()))
    matches, summary = _run(invoices, stub, max_calls=1)
    assert len(stub.requests) == 1 and summary.live_calls == 1
    assert [a.status for a in summary.attempts] == ["ok", "budget", "budget"]
    assert len(matches) == 1


def test_errors_are_recorded_and_setup_errors_stop_the_run():
    class APIConnectionError(Exception):
        pass

    class AuthenticationError(Exception):
        pass

    invoices = [_inv(i) for i in range(4)]
    stub = Stub(APIConnectionError("network down"), _response(_answer()), AuthenticationError("bad key"))
    matches, summary = _run(invoices, stub)
    assert [a.status for a in summary.attempts] == ["error", "ok", "error"]
    assert "network down" in summary.attempts[0].error
    assert summary.stopped and "bad key" in summary.stopped
    assert len(stub.requests) == 3, "the fourth invoice is never sent after a setup error"
    assert len(matches) == 1


def test_cached_responses_are_reused_without_calling(tmp_path):
    path = tmp_path / "cache.jsonl"
    invoices = [_inv(0), _inv(1)]
    _run(invoices, Stub(_response(_answer()), _response(_answer(ref="BOIL-B"))), cache=ResponseCache(path))

    class Exploding:
        def __call__(self, kwargs):
            raise AssertionError("must not call: both answers are cached")

    matches, summary = _run(invoices, Exploding(), cache=ResponseCache(path))
    assert summary.live_calls == 0 and summary.cached_calls == 2
    assert sorted(m.component_id for m in matches) == ["G-BOIL-B", "G-DHW-B"]
    assert summary.cost_usd(4.0, 20.0) == 0.0, "cached answers cost nothing"


def test_request_shape_and_what_claude_is_not_shown():
    inv = _inv(0, fund="reserve")
    kwargs = build_request(inv, ASSOCS[0], COMPS, _unsure(inv), "claude-opus-5-5", "low", 4000)
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["output_config"]["effort"] == "low"
    assert kwargs["output_config"]["format"]["type"] == "json_schema"
    policy, study = kwargs["system"]
    assert policy["text"] == POLICY and "cache_control" not in policy
    assert study["cache_control"] == {"type": "ephemeral"}
    assert "DHW-B | Domestic water heaters" in study["text"]
    user = kwargs["messages"][0]["content"]
    assert "anode rod Bldg B" in user
    everything = json.dumps(kwargs).lower()
    assert "reserve" not in user.lower() and "fund" not in everything.replace("refund", "")


def test_service_stores_matches_and_every_attempt(env, tmp_path):
    from app.db.models import InvoiceMatch, LLMAttemptRecord
    from app.db.session import session_scope
    from app.services.llm_matching import combined_matches, run_llm_matching
    from app.services.matching import run_rule_matching
    from app.synth.generator import generate
    from app.synth.io import load_dataset, write_dataset

    out = tmp_path / "synth"
    write_dataset(*generate(seed=3, n_associations=4), out)
    with session_scope() as db:
        load_dataset(db, out)
    with session_scope() as db:
        counts = run_rule_matching(db)

    class AlwaysUnsureUntilBudget:
        def __call__(self, kwargs):
            return _response(_answer(kind="routine", ref=None))

    with session_scope() as db:
        report = run_llm_matching(db, transport=AlwaysUnsureUntilBudget(), max_calls=5, cache_path=tmp_path / "c.jsonl")
    assert report["unsure_invoices"] == counts["unsure"]
    assert report["live_calls"] == 5 and report["attempts_by_status"]["ok"] == 5
    assert report["attempts_by_status"]["budget"] == counts["unsure"] - 5
    with session_scope() as db:
        assert db.scalar(select(func.count()).select_from(LLMAttemptRecord)) == counts["unsure"]
        assert db.scalar(select(func.count()).where(InvoiceMatch.method == "llm")) == 5
        combined = combined_matches(db)
        assert sum(m.method == "llm" for m in combined) == 5
        assert len(combined) == sum(v for k, v in counts.items() if k != "flagged_wrong_fund")
