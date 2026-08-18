"""Part 2 MVP — the 8 metrics the user actually needs to answer "أين يظهر
متجري؟ من يظهر قبلي؟" Deliberately not the full 14-metric spec from the
original Part 2 plan — start narrow, add the rest once answer-analysis
quality is confirmed against real data (explicit user direction).

Same discipline as app.ai_visibility.metrics (V1): every rate's denominator
is the honestly-measurable successful set, never the attempted set, and an
empty/zero-data case returns None for a rate rather than fabricating 0.0 —
0.0 would read as "measured and found zero," which is a different claim
from "nothing to measure."

Field names never say "actual_visibility"/"الظهور الفعلي" — reserved for a
future, separate Search Console integration (same rule as V1's own
metrics.py docstring)."""

import uuid
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlmodel import Session, select

from app.competitors.classification import classify_known_domain
from app.core.domain import registered_domain
from app.core.urls import normalize_hostname
from app.models.visibility_run import EngineAnswer, EngineAnswerAnalysis, VisibilityRun


@dataclass
class VisibilityMetricsV2:
    successful_answers: int
    mention_rate: float | None
    recommendation_rate: float | None
    avg_recommendation_rank: float | None
    top_3_rate: float | None
    share_of_voice: float | None
    citation_rate: float | None
    top_competitor: str | None
    top_competitor_mentions: int
    # SIGNUP re-scope — engine-agnostic report numbers (blend chatgpt+google,
    # never split in the API/UI layer; the underlying rows still carry
    # `engine` for internal audit). mention_rank (not recommendation_rank)
    # is the universal "did it appear, and where" signal both a ChatGPT
    # answer and a Google result share — recommendation_rank stays
    # ChatGPT-only and is kept above unmodified for the existing dashboard.
    total_searches: int = 0
    mentioned_count: int = 0
    avg_mention_rank: float | None = None
    top3_count: int = 0


def _empty_metrics(successful_answers: int = 0, total_searches: int = 0) -> VisibilityMetricsV2:
    return VisibilityMetricsV2(
        successful_answers=successful_answers, mention_rate=None, recommendation_rate=None,
        avg_recommendation_rank=None, top_3_rate=None, share_of_voice=None, citation_rate=None,
        top_competitor=None, top_competitor_mentions=0, total_searches=total_searches,
    )


def compute_visibility_metrics(
    session: Session, visibility_run_id: uuid.UUID, client_hostname: str | None = None
) -> VisibilityMetricsV2:
    all_attempted = session.exec(
        select(EngineAnswer).where(EngineAnswer.visibility_run_id == visibility_run_id)
    ).all()
    total_searches = len(all_attempted)

    answers = [a for a in all_attempted if a.status == "success"]
    if not answers:
        return _empty_metrics(total_searches=total_searches)

    answer_ids = [a.id for a in answers]
    analyses = session.exec(
        select(EngineAnswerAnalysis).where(EngineAnswerAnalysis.engine_answer_id.in_(answer_ids))  # type: ignore[attr-defined]
    ).all()
    if not analyses:
        return _empty_metrics(successful_answers=len(answers), total_searches=total_searches)

    total_analyzed = len(analyses)
    mentioned = [a for a in analyses if a.brand_mentioned]
    recommended = [a for a in analyses if a.mention_type == "recommended"]

    mention_rate = len(mentioned) / total_analyzed
    recommendation_rate = len(recommended) / total_analyzed

    recommendation_ranks = [a.recommendation_rank for a in analyses if a.recommendation_rank is not None]
    avg_recommendation_rank = (sum(recommendation_ranks) / len(recommendation_ranks)) if recommendation_ranks else None
    top_3_rate = (sum(1 for r in recommendation_ranks if r <= 3) / total_analyzed) if recommendation_ranks else None

    mention_ranks = [a.mention_rank for a in mentioned if a.mention_rank is not None]
    avg_mention_rank = (sum(mention_ranks) / len(mention_ranks)) if mention_ranks else None
    top3_count = sum(1 for r in mention_ranks if r <= 3)

    client_mentions = len(mentioned)
    competitor_mention_counter: Counter[str] = Counter()
    for analysis in analyses:
        for competitor in analysis.competitors_mentioned:
            name = competitor.get("name") if isinstance(competitor, dict) else None
            if name:
                competitor_mention_counter[name] += 1
    total_competitor_mentions = sum(competitor_mention_counter.values())
    share_of_voice = (
        client_mentions / (client_mentions + total_competitor_mentions)
        if (client_mentions + total_competitor_mentions) > 0
        else None
    )
    top_competitor, top_competitor_mentions = (
        competitor_mention_counter.most_common(1)[0] if competitor_mention_counter else (None, 0)
    )

    citation_rate = None
    if client_hostname:
        client_hostname = normalize_hostname(client_hostname)
        answers_with_sources = [a for a in answers if a.sources]
        if answers_with_sources:
            cites_client = sum(
                1 for a in answers_with_sources
                if any(normalize_hostname(urlparse(s.get("url", "")).hostname or "") == client_hostname for s in a.sources)
            )
            citation_rate = cites_client / len(answers_with_sources)

    return VisibilityMetricsV2(
        successful_answers=len(answers), mention_rate=mention_rate, recommendation_rate=recommendation_rate,
        avg_recommendation_rank=avg_recommendation_rank, top_3_rate=top_3_rate, share_of_voice=share_of_voice,
        citation_rate=citation_rate, top_competitor=top_competitor, top_competitor_mentions=top_competitor_mentions,
        total_searches=total_searches, mentioned_count=client_mentions, avg_mention_rank=avg_mention_rank,
        top3_count=top3_count,
    )


@dataclass
class CompetitorVisibilitySummary:
    name: str
    domain: str | None
    appearances: int
    appearance_rate: float
    avg_rank: float | None
    ahead_of_client: bool


def compute_top_competitors(
    session: Session, visibility_run_id: uuid.UUID, *, client_avg_mention_rank: float | None,
    competitor_name_to_domain: dict[str, str], limit: int | None = 5,
) -> list[CompetitorVisibilitySummary]:
    """Top competitors by how often they appeared in the same analyzed
    answers the client was measured against — reuses the exact
    competitors_mentioned data already captured by answer analysis / the
    deterministic Google pass, never a second discovery mechanism."""
    answers = session.exec(
        select(EngineAnswer).where(EngineAnswer.visibility_run_id == visibility_run_id, EngineAnswer.status == "success")
    ).all()
    if not answers:
        return []
    answer_ids = [a.id for a in answers]
    analyses = session.exec(
        select(EngineAnswerAnalysis).where(EngineAnswerAnalysis.engine_answer_id.in_(answer_ids))  # type: ignore[attr-defined]
    ).all()
    total_analyzed = len(analyses)
    if total_analyzed == 0:
        return []

    appearances_by_name: Counter[str] = Counter()
    ranks_by_name: dict[str, list[int]] = {}
    for analysis in analyses:
        for competitor in analysis.competitors_mentioned:
            name = competitor.get("name") if isinstance(competitor, dict) else None
            if not name:
                continue
            appearances_by_name[name] += 1
            rank = competitor.get("rank")
            if isinstance(rank, int):
                ranks_by_name.setdefault(name, []).append(rank)

    summaries: list[CompetitorVisibilitySummary] = []
    for name, appearances in appearances_by_name.items():
        ranks = ranks_by_name.get(name, [])
        avg_rank = (sum(ranks) / len(ranks)) if ranks else None
        ahead = (
            avg_rank is not None and client_avg_mention_rank is not None and avg_rank < client_avg_mention_rank
        )
        summaries.append(CompetitorVisibilitySummary(
            name=name, domain=competitor_name_to_domain.get(name), appearances=appearances,
            appearance_rate=round(appearances / total_analyzed, 4) if appearances else 0.0,
            avg_rank=avg_rank, ahead_of_client=ahead,
        ))

    summaries.sort(key=lambda c: c.appearances, reverse=True)
    return summaries if limit is None else summaries[:limit]


def compute_client_rank_among_competitors(mentioned_count: int, competitor_appearance_counts: list[int]) -> tuple[int, int]:
    """1-based 'competition ranking' (ties share the better rank) of the
    client among itself + every competitor that appeared at least once in
    this run's analyses, ordered by the same raw appearance count
    compute_top_competitors already sorts by. Returns (rank, total) where
    total is how many entities (client + competitors) were actually
    compared — the 'X من Y' the /signup competitors screen shows."""
    rank = 1 + sum(1 for count in competitor_appearance_counts if count > mentioned_count)
    total = len(competitor_appearance_counts) + 1
    return rank, total


@dataclass
class CitationSummary:
    domain: str
    citation_count: int
    supports: str  # "client" | "competitor" | "mixed"


# Citations from these known-domain roles are never real evidence sources
# for a merchant's own visibility — a Google/Bing "irrelevant" hit (which
# also covers maps.google.com and any google.com/url?... redirect, since
# registered_domain collapses every subdomain/path to the bare google.com
# entry already curated in app.competitors.classification) or a social
# profile isn't a citable third-party source, it's the search surface or a
# social platform itself.
_EXCLUDED_CITATION_ROLES = frozenset({"irrelevant", "social"})


def compute_top_citations(
    session: Session, visibility_run_id: uuid.UUID, *, client_hostname: str,
    competitor_domain_names: dict[str, str], limit: int = 8,
) -> list[CitationSummary]:
    """Aggregates every successful answer's sources[] across the run,
    grouped by registered domain (counted once per answer, not once per
    result position, so a domain appearing twice in one SERP page doesn't
    double-count), excluding Google/Bing/Maps/redirect and social-platform
    domains via the existing classify_known_domain registry — the same
    reuse citation_classification.py already relies on. Each domain is
    flagged 'client'/'competitor'/'mixed' by whether the answers citing it
    tended to mention the client or a competitor."""
    answers = session.exec(
        select(EngineAnswer).where(EngineAnswer.visibility_run_id == visibility_run_id, EngineAnswer.status == "success")
    ).all()
    if not answers:
        return []
    answer_ids = [a.id for a in answers]
    analyses = session.exec(
        select(EngineAnswerAnalysis).where(EngineAnswerAnalysis.engine_answer_id.in_(answer_ids))  # type: ignore[attr-defined]
    ).all()
    analysis_by_answer = {a.engine_answer_id: a for a in analyses}

    client_registered = registered_domain(client_hostname) if client_hostname else ""
    # competitor_domain_names is name -> domain (same shape compute_top_competitors
    # takes) — the registrable-domain set needs the values, not the keys.
    competitor_registered = {registered_domain(d) for d in competitor_domain_names.values()}

    citation_counts: Counter[str] = Counter()
    client_support: Counter[str] = Counter()
    competitor_support: Counter[str] = Counter()

    for answer in answers:
        analysis = analysis_by_answer.get(answer.id)
        domains_this_answer: set[str] = set()
        for source in answer.sources:
            hostname = normalize_hostname(urlparse(source.get("url", "")).hostname or "")
            if not hostname:
                continue
            domain = registered_domain(hostname)
            if domain == client_registered or domain in domains_this_answer:
                continue
            known = classify_known_domain(domain)
            if known is not None and known[0] in _EXCLUDED_CITATION_ROLES:
                continue
            domains_this_answer.add(domain)
            citation_counts[domain] += 1
            if domain in competitor_registered:
                # The source itself is a known competitor's own storefront
                # — the strongest possible "supports a competitor" signal,
                # independent of what else that answer happened to mention.
                competitor_support[domain] += 1
            elif analysis is not None and analysis.brand_mentioned:
                client_support[domain] += 1
            elif analysis is not None and analysis.competitors_mentioned:
                competitor_support[domain] += 1

    summaries: list[CitationSummary] = []
    for domain, count in citation_counts.items():
        c_support = client_support.get(domain, 0)
        comp_support = competitor_support.get(domain, 0)
        supports = "client" if c_support > comp_support else "competitor" if comp_support > c_support else "mixed"
        summaries.append(CitationSummary(domain=domain, citation_count=count, supports=supports))

    summaries.sort(key=lambda c: c.citation_count, reverse=True)
    return summaries[:limit]


def compute_week_over_week_delta(
    session: Session, store_id: uuid.UUID, current_run_id: uuid.UUID, current: VisibilityMetricsV2,
    client_hostname: str | None = None,
) -> dict | None:
    """None when there's no previous completed run to compare against —
    never a fabricated zero-change. Same 'find the previous run, diff, but
    only if one exists' pattern already used by alert_engine.py."""
    previous_run = session.exec(
        select(VisibilityRun)
        .where(VisibilityRun.store_id == store_id, VisibilityRun.status == "completed", VisibilityRun.id != current_run_id)
        .order_by(VisibilityRun.completed_at.desc())  # type: ignore[union-attr]
    ).first()
    if previous_run is None:
        return None

    previous = compute_visibility_metrics(session, previous_run.id, client_hostname)
    if previous.successful_answers == 0:
        return None

    def _delta(a: float | None, b: float | None) -> float | None:
        return round(a - b, 4) if a is not None and b is not None else None

    return {
        "previous_run_id": str(previous_run.id),
        "mention_rate_delta": _delta(current.mention_rate, previous.mention_rate),
        "recommendation_rate_delta": _delta(current.recommendation_rate, previous.recommendation_rate),
        "share_of_voice_delta": _delta(current.share_of_voice, previous.share_of_voice),
        "top_3_rate_delta": _delta(current.top_3_rate, previous.top_3_rate),
    }
