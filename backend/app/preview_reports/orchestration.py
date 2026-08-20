"""Stage 12 (spec) — the single job that builds one complete PreviewReport.
Runs every stage (crawl -> understanding -> queries -> search -> visibility
-> competitors -> recommendation) in memory and writes the assembled
report blob in one final commit when everything succeeds — the only
client-visible state transition is processing -> ready or
processing -> failed, exactly per app.models.preview_report's design.

`report.stage` IS committed progressively (a handful of small commits
between stages) — this is deliberately not a violation of that guarantee:
`stage` is never returned by any client-facing endpoint (only `status`
is, and `status` itself stays "processing" until the very end), so a
client can never observe or race against a partial pipeline. It exists
purely so a stuck/slow report can be diagnosed ("stuck at stage=searching")
per the spec's own observability requirement.

A failure at any stage is caught here and turns into status="failed" with
error_message set — never a raised exception that would leave the row
stuck at "processing" forever, and never a partial report silently marked
"ready"."""

from datetime import datetime, timezone

from sqlmodel import Session

from app.core.config import Settings
from app.core.evaluation_mode import LiveProviderBlockedError
from app.models.preview_report import PreviewReport
from app.preview_reports.competitors import extract_competitors
from app.preview_reports.crawl import crawl_for_preview
from app.preview_reports.queries import generate_search_queries
from app.preview_reports.recommendation import build_recommendation
from app.preview_reports.search import run_preview_searches
from app.preview_reports.understanding import build_understanding, extract_deterministic_facts
from app.preview_reports.visibility import classify_visibility, compute_visibility_scores, enrich_query_results
from app.providers.ai.router import ModelRouter
from app.providers.search import get_search_provider
from app.providers.search.base import SearchProvider


def _checkpoint(session: Session, report: PreviewReport, stage: str) -> None:
    report.stage = stage
    session.add(report)
    session.commit()


def _resolve_search_provider(session: Session) -> SearchProvider | None:
    """Google being unconfigured/blocked must degrade every query's
    google leg to a failed status (see app.preview_reports.search), never
    abort the whole report — mirrors get_search_provider's own mock/
    replay/live modes, just with a None fallback on top for the live-
    blocked case instead of letting the job crash on startup."""
    try:
        return get_search_provider(session)
    except LiveProviderBlockedError:
        return None


async def generate_preview_report(
    *, session: Session, report: PreviewReport, router: ModelRouter, settings: Settings
) -> PreviewReport:
    try:
        _checkpoint(session, report, "crawling")
        pages = await crawl_for_preview(report.store_url, settings)
        facts = extract_deterministic_facts(pages, report.store_url)

        _checkpoint(session, report, "understanding")
        understanding = await build_understanding(session=session, router=router, facts=facts)

        _checkpoint(session, report, "generating_queries")
        queries = generate_search_queries(
            facts, target_count=settings.preview_search_ai_query_count, fallback_category=understanding.get("category")
        )

        _checkpoint(session, report, "searching")
        search_provider = _resolve_search_provider(session)
        raw_results = await run_preview_searches(
            router=router,
            session=session,
            queries=queries,
            settings=settings,
            search_provider=search_provider,
            google_query_limit=settings.preview_search_google_query_count,
        )

        _checkpoint(session, report, "analyzing_visibility")
        enriched = enrich_query_results(
            raw_results,
            brand_name=understanding["brand_name"],
            domain=facts["domain"],
            aliases=[a for a in (facts.get("og_site_name"), facts.get("title")) if a],
        )
        visibility_scores = compute_visibility_scores(enriched)

        _checkpoint(session, report, "extracting_competitors")
        competitors = extract_competitors(enriched, store_domain=facts["domain"])
        visibility = classify_visibility(visibility_scores, enriched, competitors)

        _checkpoint(session, report, "generating_recommendation")
        recommendation = await build_recommendation(
            session=session, router=router, understanding=understanding, enriched_queries=enriched
        )

        generated_at = datetime.now(timezone.utc)
        report.report = {
            "id": str(report.id),
            "status": "ready",
            "store": {
                "url": report.store_url,
                "domain": facts["domain"],
                "logo": facts.get("og_image") or facts.get("favicon"),
                "brand_name": understanding["brand_name"],
                "category": understanding["category"],
                "categories": facts["category_names"][:5],
                "products": understanding["products"],
                "is_online_store": understanding["is_online_store"],
            },
            "visibility": visibility,
            "competitors": competitors,
            "queries": enriched,
            "recommendation": recommendation,
            "generated_at": generated_at.isoformat(),
        }
        report.status = "ready"
        report.stage = "ready"
        report.completed_at = generated_at
        session.add(report)
        session.commit()
        session.refresh(report)
        return report
    except Exception as exc:  # noqa: BLE001 — persisted failure is the job contract; nothing may propagate and leave the row stuck at "processing"
        session.rollback()
        report.status = "failed"
        report.error_message = str(exc)[:2000]
        session.add(report)
        session.commit()
        session.refresh(report)
        return report
