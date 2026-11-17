"""
Ask Claude about the invoices the rules left unsure. Every invoice-matching model call goes through
this module.

Division of labour:

* **Claude decides only the fuzzy part:** is this invoice routine upkeep, or work on one of the
  association's reserve components, and which one? It may also answer ``unsure``.
* **Code decides everything numeric and checkable.** Repair vs replacement comes from the same
  15%-of-inflated-cost rule the rules use, wrong-fund flags from the same comparison, and a
  component reference must exist in the association's reserve study or the answer is rejected.

Claude sees what a client hands over (vendor, date, amount, memo, the reserve study) and what the
rules noticed. It never sees the fund an invoice was booked to, and never the answer key.

Every attempt is recorded, including refusals, truncations, invalid answers, API errors and calls
skipped by the budget. Responses are cached on disk by request hash, so re-running or re-scoring
never pays twice, and tests can run on stored responses.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError

from app.domain.matching import (
    CAPITAL_THRESHOLD,
    AssociationLike,
    ComponentLike,
    InvoiceLike,
    MatchResult,
    fund_flag,
    memo_building,
    vendor_trade,
    with_work_type,
)

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
CONFIDENCE = {"high": 0.85, "medium": 0.65, "low": 0.45}
# SDK errors that mean every later call would fail too. Rate limits, timeouts, connection errors and
# 5xx are retried by the SDK (2 retries) and, if they still fail, recorded per invoice.
FATAL_ERRORS = {"AuthenticationError", "PermissionDeniedError", "NotFoundError", "BadRequestError"}


class InvoiceAnswer(BaseModel):
    """The JSON Claude must return."""

    kind: Literal["routine", "component", "unsure"]
    component_ref: str | None
    confidence: Literal["high", "medium", "low"]
    reason: str


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["routine", "component", "unsure"]},
        "component_ref": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["kind", "component_ref", "confidence", "reason"],
    "additionalProperties": False,
}

POLICY = f"""You sort vendor invoices for a homeowner or condo association against its reserve study.

The reserve study lists the association's major common-area components (roofs, boilers, paving
and so on), each with a reference code. For one invoice, decide:

- "routine": ordinary upkeep that is not work on any listed component, such as grounds contracts,
  cleaning, pest control, snow removal, trash, or management services.
- "component": repair or replacement work on exactly one listed component. Give its reference code
  exactly as written in the study. If the work touches two components, give the main one.
- "unsure": you can't tell which component, or whether it's routine, from what the invoice says.
  Prefer "unsure" to a guess: a person reviews every unsure invoice.

Use trade knowledge. Memos are written by contractors, often in jargon and abbreviations, and
sometimes name the wrong building. The vendor's trade and the amount are evidence too: large
amounts relative to a component's cost suggest replacement work on that component; a few hundred
dollars from a grounds company is usually routine.

You don't decide repair vs replacement: the association's policy classifies work at
{CAPITAL_THRESHOLD:.0%} or more of a component's replacement cost as a replacement, and code
applies it after you answer.

Return only the JSON object. Keep "reason" to one short sentence naming the evidence you used."""


# --------------------------------------------------------------------------------------- results
@dataclass
class LLMAttempt:
    """One invoice's trip through this module, whatever happened."""

    invoice_id: str
    status: str  # ok | unsure | invalid | refused | truncated | error | budget
    model: str
    from_cache: bool = False
    component_id: str | None = None
    answer: dict | None = None
    raw_text: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    request_id: str | None = None


@dataclass
class LLMRunSummary:
    attempts: list[LLMAttempt] = field(default_factory=list)
    live_calls: int = 0
    cached_calls: int = 0
    stopped: str | None = None  # set when a fatal error ended the run early

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for a in self.attempts:
            out[a.status] = out.get(a.status, 0) + 1
        return dict(sorted(out.items()))

    def tokens(self) -> dict[str, int]:
        live = [a for a in self.attempts if not a.from_cache]
        return {
            "input": sum(a.input_tokens for a in live),
            "output": sum(a.output_tokens for a in live),
            "cache_read": sum(a.cache_read_tokens for a in live),
            "cache_write": sum(a.cache_write_tokens for a in live),
        }

    def cost_usd(self, input_price: float, output_price: float) -> float:
        """Estimate at list prices. Cache reads bill at 0.1x input and writes at 1.25x."""
        t = self.tokens()
        dollars = (
            t["input"] * input_price
            + t["cache_read"] * input_price * 0.1
            + t["cache_write"] * input_price * 1.25
            + t["output"] * output_price
        )
        return round(dollars / 1_000_000, 4)


# --------------------------------------------------------------------------------------- transport
class ResponseLike(Protocol):
    stop_reason: str | None
    content: list[Any]
    usage: Any


Transport = Callable[[dict[str, Any]], ResponseLike]


def anthropic_transport(provider: str, aws_region: str) -> Transport:
    """A transport that calls Claude through the official SDK.

    On the Claude API it opts into server-side refusal fallbacks. Bedrock has no server-side
    fallbacks, so a refusal there is recorded as a failed attempt.
    """
    import anthropic  # optional dependency: pip install ".[llm]"

    if provider == "bedrock":
        client = anthropic.AnthropicBedrockMantle(aws_region=aws_region)

        def send(kwargs: dict[str, Any]) -> ResponseLike:
            return client.messages.create(**{**kwargs, "model": f"anthropic.{kwargs['model']}"})

        return send
    if provider != "anthropic":
        raise ValueError(f"unknown match_llm_provider {provider!r}")
    client = anthropic.Anthropic()

    def send_first_party(kwargs: dict[str, Any]) -> ResponseLike:
        return client.beta.messages.create(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")

    return send_first_party


# --------------------------------------------------------------------------------------- prompt
def study_block(assoc: AssociationLike, components: Sequence[ComponentLike]) -> str:
    """The association's reserve study as the model sees it. Stable per association (cacheable)."""
    lines = [
        f"Association {assoc.id}. Reserve study year {assoc.study_year}; costs grow {assoc.inflation_rate:.2%} a year.",
        "Components (ref | name | category | location | replacement cost in study-year dollars):",
    ]
    for c in sorted(components, key=lambda c: c.id):
        ref = c.id.split("-", 1)[1] if c.id.startswith(f"{assoc.id}-") else c.id
        lines.append(f"{ref} | {c.name} | {c.category} | {c.location or 'whole site'} | ${c.replacement_cost:,.0f}")
    return "\n".join(lines)


def invoice_block(inv: InvoiceLike, rule: MatchResult) -> str:
    """One invoice, plus what the rules noticed. No booked fund, no answer key."""
    return "\n".join(
        [
            f"Vendor: {inv.vendor_name}",
            f"Date: {inv.invoice_date.isoformat()}",
            f"Amount: ${inv.amount:,.2f}",
            f"Memo: {inv.memo}",
            f"Rules noticed: vendor trade {vendor_trade(inv.vendor_name) or 'unknown'}; "
            f"building in memo {memo_building(inv.memo) or 'none'}; {rule.reasons[-1] if rule.reasons else ''}",
        ]
    )


def build_request(
    inv: InvoiceLike,
    assoc: AssociationLike,
    components: Sequence[ComponentLike],
    rule: MatchResult,
    model: str,
    effort: str,
    max_tokens: int,
) -> dict[str, Any]:
    """Messages API arguments. The policy and the study come first and are cached; the invoice varies."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
        "system": [
            {"type": "text", "text": POLICY},
            {"type": "text", "text": study_block(assoc, components), "cache_control": {"type": "ephemeral"}},
        ],
        "messages": [{"role": "user", "content": invoice_block(inv, rule)}],
    }


def request_key(kwargs: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------------------- cache
class ResponseCache:
    """Append-only JSONL file of model responses keyed by request hash."""

    def __init__(self, path: Path | None):
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        if path and path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.entries[row["key"]] = row

    def get(self, key: str) -> dict[str, Any] | None:
        return self.entries.get(key)

    def put(self, key: str, row: dict[str, Any]) -> None:
        row = {"key": key, **row}
        self.entries[key] = row
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")


def _response_row(resp: ResponseLike) -> dict[str, Any]:
    text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
    usage = resp.usage
    return {
        "stop_reason": resp.stop_reason,
        "text": text,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
        },
        "request_id": getattr(resp, "_request_id", None),
    }


# --------------------------------------------------------------------------------------- matching
def _interpret(
    attempt: LLMAttempt,
    row: dict[str, Any],
    inv: InvoiceLike,
    assoc: AssociationLike,
    by_ref: dict[str, ComponentLike],
) -> MatchResult | None:
    """Fill in the attempt from a response row; return a match if the answer is usable."""
    usage = row["usage"]
    attempt.raw_text = row["text"]
    attempt.request_id = row.get("request_id")
    attempt.input_tokens = usage["input_tokens"]
    attempt.output_tokens = usage["output_tokens"]
    attempt.cache_read_tokens = usage["cache_read_input_tokens"]
    attempt.cache_write_tokens = usage["cache_creation_input_tokens"]
    if row["stop_reason"] == "refusal":
        attempt.status, attempt.error = "refused", "model declined"
        return None
    if row["stop_reason"] == "max_tokens":
        attempt.status, attempt.error = "truncated", "hit max_tokens"
        return None
    try:
        answer = InvoiceAnswer.model_validate_json(row["text"])
    except ValidationError as exc:
        attempt.status, attempt.error = "invalid", f"answer doesn't fit the schema: {exc.errors()[0]['msg']}"
        return None
    attempt.answer = answer.model_dump()
    reason = f"claude ({answer.confidence}): {answer.reason}"
    if answer.kind == "unsure":
        attempt.status = "unsure"
        return None
    if answer.kind == "routine":
        if answer.component_ref:
            attempt.status, attempt.error = "invalid", "routine answer named a component"
            return None
        attempt.status = "ok"
        result = MatchResult(inv.id, "routine", None, CONFIDENCE[answer.confidence], [reason], method="llm")
        fund_flag(result, inv)
        return result
    comp = by_ref.get(answer.component_ref or "")
    if comp is None:
        attempt.status = "invalid"
        attempt.error = f"component {answer.component_ref!r} is not in this association's reserve study"
        return None
    attempt.status, attempt.component_id = "ok", comp.id
    result = with_work_type(inv, comp, assoc, CONFIDENCE[answer.confidence], [reason])
    result.method = "llm"
    fund_flag(result, inv)
    return result


def match_unsure_with_llm(
    invoices: Sequence[InvoiceLike],
    components: Sequence[ComponentLike],
    associations: Sequence[AssociationLike],
    rule_results: Sequence[MatchResult],
    transport: Transport | None,
    cache: ResponseCache,
    *,
    model: str,
    effort: str = "low",
    max_tokens: int = 4000,
    max_calls: int = 10,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list[MatchResult], LLMRunSummary]:
    """Ask Claude about every invoice the rules left unsure.

    Cached responses are always used. Live calls stop at ``max_calls``; the rest are recorded as
    ``budget`` attempts. With ``transport=None`` only cached responses are used.
    Returns the usable matches (method "llm") and a summary with every attempt.
    """
    invs = {i.id: i for i in invoices}
    assocs = {a.id: a for a in associations}
    comps_by_assoc: dict[str, list[ComponentLike]] = {}
    for c in components:
        comps_by_assoc.setdefault(c.association_id, []).append(c)
    unsure = [r for r in rule_results if r.label == "unsure"]
    # Group by association so consecutive calls share the cached study prefix.
    unsure.sort(key=lambda r: (invs[r.invoice_id].association_id, invs[r.invoice_id].invoice_date, r.invoice_id))

    summary = LLMRunSummary()
    matches: list[MatchResult] = []
    for rule in unsure:
        inv = invs[rule.invoice_id]
        assoc = assocs[inv.association_id]
        comps = comps_by_assoc.get(assoc.id, [])
        by_ref = {c.id.split("-", 1)[1]: c for c in comps}
        kwargs = build_request(inv, assoc, comps, rule, model, effort, max_tokens)
        key = request_key(kwargs)
        attempt = LLMAttempt(inv.id, "error", model)
        row = cache.get(key)
        if row is not None:
            attempt.from_cache = True
            summary.cached_calls += 1
        elif transport is None or summary.live_calls >= max_calls:
            attempt.status, attempt.error = "budget", "not asked: call budget reached or no live transport"
            summary.attempts.append(attempt)
            continue
        else:
            summary.live_calls += 1
            started = clock()
            try:
                row = _response_row(transport(kwargs))
            except Exception as exc:  # every failure is recorded; the invoice stays unsure
                attempt.status, attempt.error = "error", f"{type(exc).__name__}: {exc}"
                attempt.latency_ms = int((clock() - started) * 1000)
                summary.attempts.append(attempt)
                if type(exc).__name__ in FATAL_ERRORS:
                    # A setup problem (key, model id, request shape) fails every call the same way:
                    # stop instead of spending the budget on it.
                    log.error("Stopping Claude matching after %s: %s", inv.id, attempt.error)
                    summary.stopped = attempt.error
                    break
                log.warning("Claude call failed for %s: %s", inv.id, attempt.error)
                continue
            attempt.latency_ms = int((clock() - started) * 1000)
            cache.put(key, {"model": model, **row})
        result = _interpret(attempt, row, inv, assoc, by_ref)
        summary.attempts.append(attempt)
        if result is not None:
            matches.append(result)
    return matches, summary


def attempts_as_dicts(summary: LLMRunSummary) -> list[dict[str, Any]]:
    return [asdict(a) for a in summary.attempts]
