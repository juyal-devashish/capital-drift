"""Run Claude over the invoices the rules left unsure, and store matches and every attempt."""

import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.invoice_llm import (
    LLMRunSummary,
    ResponseCache,
    Transport,
    anthropic_transport,
    match_unsure_with_llm,
)
from app.core.config import get_settings
from app.db.models import Association, Invoice, InvoiceMatch, LLMAttemptRecord, ReserveComponent
from app.domain.matching import MatchResult


def stored_matches(db: Session, method: str) -> list[MatchResult]:
    rows = db.scalars(select(InvoiceMatch).where(InvoiceMatch.method == method))
    return [
        MatchResult(m.invoice_id, m.label, m.component_id, m.confidence, list(m.reasons), list(m.flags), m.method)
        for m in rows
    ]


def run_llm_matching(
    db: Session,
    *,
    transport: Transport | None = None,
    live: bool = True,
    max_calls: int | None = None,
    cache_path: Path | None = None,
) -> dict:
    """Ask Claude about every invoice whose rule match is unsure. Needs `match` to have run first.

    ``live=False`` uses cached responses only (no cost). Otherwise a transport is built from
    settings unless one is passed in (tests pass a stub).
    """
    settings = get_settings()
    rule_results = stored_matches(db, "rules")
    invoices = list(db.scalars(select(Invoice)))
    if len(rule_results) != len(invoices):
        raise RuntimeError(f"{len(rule_results)} rule matches for {len(invoices)} invoices; run `match` first")
    if live and transport is None:
        transport = anthropic_transport(settings.match_llm_provider, settings.match_llm_aws_region)
    cache = ResponseCache(cache_path or settings.data_dir / settings.match_llm_cache_file)

    matches, summary = match_unsure_with_llm(
        invoices,
        list(db.scalars(select(ReserveComponent))),
        list(db.scalars(select(Association))),
        rule_results,
        transport if live else None,
        cache,
        model=settings.match_llm_model,
        effort=settings.match_llm_effort,
        max_tokens=settings.match_llm_max_tokens,
        max_calls=settings.match_llm_max_calls if max_calls is None else max_calls,
    )

    run_id = str(uuid.uuid4())
    db.execute(delete(InvoiceMatch).where(InvoiceMatch.method == "llm"))
    db.add_all(
        InvoiceMatch(
            invoice_id=m.invoice_id,
            method="llm",
            label=m.label,
            component_id=m.component_id,
            confidence=m.confidence,
            reasons=m.reasons,
            flags=m.flags,
        )
        for m in matches
    )
    db.add_all(LLMAttemptRecord(run_id=run_id, **_attempt_fields(a)) for a in summary.attempts)
    db.flush()
    return _report(run_id, summary, len(matches), settings)


def _attempt_fields(a) -> dict:
    return {
        "invoice_id": a.invoice_id,
        "status": a.status,
        "model": a.model,
        "from_cache": a.from_cache,
        "component_id": a.component_id,
        "answer": a.answer,
        "raw_text": a.raw_text,
        "error": a.error,
        "input_tokens": a.input_tokens,
        "output_tokens": a.output_tokens,
        "cache_read_tokens": a.cache_read_tokens,
        "cache_write_tokens": a.cache_write_tokens,
        "latency_ms": a.latency_ms,
        "request_id": a.request_id,
    }


def _report(run_id: str, summary: LLMRunSummary, n_matches: int, settings) -> dict:
    return {
        "run_id": run_id,
        "model": settings.match_llm_model,
        "provider": settings.match_llm_provider,
        "unsure_invoices": len(summary.attempts),
        "attempts_by_status": summary.counts(),
        "matches_stored": n_matches,
        "live_calls": summary.live_calls,
        "cached_calls": summary.cached_calls,
        "stopped_early": summary.stopped,
        "tokens": summary.tokens(),
        "estimated_cost_usd": summary.cost_usd(settings.match_llm_input_price, settings.match_llm_output_price),
    }


def reviewed_matches(db: Session) -> list[MatchResult]:
    """What the review queue works from: a property manager's answer, else ``combined_matches``.

    Kept apart from ``combined`` so the day 4-5 numbers (rules + Claude) still reproduce after reviews.
    """
    reviewer = {m.invoice_id: m for m in stored_matches(db, "reviewer")}
    return [reviewer.get(m.invoice_id, m) for m in combined_matches(db)]


def combined_matches(db: Session) -> list[MatchResult]:
    """Rules first; where the rules were unsure and Claude gave a usable answer, Claude's answer."""
    llm = {m.invoice_id: m for m in stored_matches(db, "llm")}
    return [llm.get(r.invoice_id, r) if r.label == "unsure" else r for r in stored_matches(db, "rules")]
