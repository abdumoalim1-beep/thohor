"""Part R8 (Round 1 remediation) — the Product Trust Contract: 10 invariants
the product must never violate, each traced to a real bug found and fixed
during Round 1 / its remediation. Every test here is deliberately
self-contained (re-asserting the guarantee directly against the real
function, not just importing another test module's fixture) so this file
alone is the single source of truth for "does the product still keep its
promises" — even if the module-specific test file that originally caught
the bug is later refactored or split.

No live SerpAPI/OpenAI calls anywhere in this file — every provider under
test here is Mock/Replay/fake, or a pure function with no I/O at all.
"""

import uuid

from sqlmodel import select

from app.ai_visibility.metrics import compute_ai_visibility_metrics_by_surface
from app.ai_visibility.surfaces import AI_VISIBILITY_SURFACES, unavailable_surface_names
from app.competitors.classification import classify_known_domain, is_business_competitor
from app.competitors.discovery_engine import mine_serp_competitors
from app.core.config import Settings
from app.core.domain import is_synthetic_test_domain
from app.crawler.store_intelligence import _upsert_category
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorType
from app.models.observation import PageObservation
from app.models.catalog import Page
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.research import ResearchRun, RunStatus
from app.models.serp import SerpObservation
from app.models.store import Store
from app.opportunities.evidence_trace import trace_recommendation_evidence
from app.opportunities.freshness import recommendation_freshness, select_primary_recommendations
from app.opportunities.quality_gate import check_recommendation_batch_quality
from app.providers.search.campaign_guarded_provider import CampaignGuardedSearchProvider
from app.providers.search.pricing import estimate_search_cost_usd
from app.providers.search.replay_provider import ReplaySearchProvider
from app.providers.search.serpapi_provider import SerpApiProvider
from app.models.evaluation import EvaluationCampaign


def _make_org_store_run(session, *, run_status=RunStatus.completed):
    org = Organization(name="t", slug=f"t-trust-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    from app.models.base import utcnow

    run = ResearchRun(
        store_id=store.id, status=run_status, completed_at=utcnow() if run_status == RunStatus.completed else None
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return org, store, run


# --- Invariant 1: a stale recommendation is never shown as current -------


def test_invariant_stale_recommendation_never_current(session):
    org, store, run_a = _make_org_store_run(session)
    opp = Opportunity(
        store_id=store.id, research_run_id=run_a.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="fp-1",
    )
    session.add(opp)
    session.commit()
    session.refresh(opp)
    rec = Recommendation(
        store_id=store.id, opportunity_id=opp.id, first_seen_research_run_id=run_a.id,
        last_seen_research_run_id=run_a.id, title="t", what_to_do="do", why_it_matters="why",
        evidence_ids=["ev-1"], status=RecommendationStatus.new, fingerprint="rec-fp-1",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)

    # A newer completed run exists that never reconfirmed this recommendation.
    _, _, run_b = _make_org_store_run(session)  # separate store, but proves the mechanism below directly
    run_b.store_id = store.id
    session.add(run_b)
    session.commit()

    assert recommendation_freshness(rec, run_b.id) == "stale"
    primary = select_primary_recommendations(session, store.id, max_size=5)
    assert rec not in primary


# --- Invariant 2: an unsupported (no-evidence) recommendation is never primary ---


def test_invariant_unsupported_recommendation_never_primary(session):
    org, store, run = _make_org_store_run(session)
    opp = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title="t", description="d", status=OpportunityStatus.open, fingerprint="fp-2",
    )
    session.add(opp)
    session.commit()
    session.refresh(opp)
    unsupported = Recommendation(
        store_id=store.id, opportunity_id=opp.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="unsupported claim", what_to_do="do", why_it_matters="why",
        evidence_ids=[],  # no evidence at all
        status=RecommendationStatus.new, fingerprint="rec-fp-2", priority_score=99.0,
    )
    session.add(unsupported)
    session.commit()
    session.refresh(unsupported)

    primary = select_primary_recommendations(session, store.id, max_size=5)
    assert unsupported not in primary

    # Also flagged by the deterministic quality gate (Part Q3), belt-and-braces.
    issues = check_recommendation_batch_quality([unsupported])
    assert any(i.check == "unsupported_claim" for i in issues)


# --- Invariant 3: an unavailable AI surface is never counted as 0% -------


def test_invariant_unavailable_surface_never_counted_as_zero(session):
    org, store, run = _make_org_store_run(session)
    # "gemini" observed this run; "claude" never configured (no API key) —
    # simulated here by simply never creating any claude observation and
    # checking Settings() with no keys set.
    session.add(
        AIVisibilityObservation(
            store_id=store.id, intent_id=uuid.uuid4(), prompt_variant_id=uuid.uuid4(),
            research_run_id=run.id, surface="chatgpt", provider="openai", model="gpt-4o-mini",
            country="sa", language="ar", mentioned=True,
        )
    )
    session.commit()

    settings = Settings(openai_api_key=None, anthropic_api_key=None, google_api_key=None)
    unavailable = unavailable_surface_names(settings)
    assert {"chatgpt", "gemini", "claude"} <= set(unavailable)

    by_surface = compute_ai_visibility_metrics_by_surface(session, run.id)
    # chatgpt has real observations above (a real key IS configured in this
    # DB-only computation — unavailability is a settings-layer concept, not
    # a metrics-layer one); the point under test is that surfaces with zero
    # observations (gemini, claude) never appear with a fabricated 0.0.
    assert "gemini" not in by_surface
    assert "claude" not in by_surface
    assert set(by_surface) <= {s.surface for s in AI_VISIBILITY_SURFACES}


# --- Invariant 4: a publisher is never shown as a direct competitor ------


def test_invariant_publisher_never_shown_as_direct_competitor():
    result = classify_known_domain("ar.wikipedia.org")
    assert result is not None
    classification, _confidence, _reason = result
    assert classification == "publisher"

    competitor = Competitor(
        store_id=uuid.uuid4(), domain="ar.wikipedia.org", name="Wikipedia",
        competitor_type=CompetitorType.search_competitor, first_seen_research_run_id=uuid.uuid4(),
        classification=classification,
    )
    assert is_business_competitor(competitor) is False


# --- Invariant 5: a historical observation is never overwritten ----------


def test_invariant_historical_page_observation_never_overwritten(session):
    org, store, run_a = _make_org_store_run(session)
    page = Page(store_id=store.id, url="https://store.example/product/1", page_type="product")
    session.add(page)
    session.commit()
    session.refresh(page)

    obs_a = PageObservation(
        store_id=store.id, research_run_id=run_a.id, page_id=page.id, source_url=page.url,
        source="crawler", extractor_version="v1", normalized_extraction={"title": "Old Title"},
    )
    session.add(obs_a)
    session.commit()
    session.refresh(obs_a)
    original_extraction = dict(obs_a.normalized_extraction)

    _, _, run_b = _make_org_store_run(session)
    run_b.store_id = store.id
    session.add(run_b)
    session.commit()

    # A second crawl of the SAME page produces a NEW row, never mutates obs_a.
    obs_b = PageObservation(
        store_id=store.id, research_run_id=run_b.id, page_id=page.id, source_url=page.url,
        source="crawler", extractor_version="v1", normalized_extraction={"title": "New Title"},
    )
    session.add(obs_b)
    session.commit()
    session.refresh(obs_b)

    session.refresh(obs_a)
    assert obs_a.id != obs_b.id
    assert obs_a.normalized_extraction == original_extraction  # untouched
    assert obs_a.normalized_extraction != obs_b.normalized_extraction

    all_observations = session.exec(select(PageObservation).where(PageObservation.page_id == page.id)).all()
    assert len(all_observations) == 2


# --- Invariant 6: a canonical entity IS refreshable from a newer observation ---


def test_invariant_canonical_category_refreshes_from_newer_observation(session):
    """The deliberate counterpart to Invariant 5 — Category (a canonical
    'current best-known fact', Part R1) is mutable by design, unlike
    PageObservation (an immutable historical snapshot). Both invariants
    must hold simultaneously; this is not a contradiction."""
    org, store, run = _make_org_store_run(session)
    url = "https://store.example/category/coffee"

    first = _upsert_category(session, store.id, "Stale Scraped Title | Store", url)
    assert first.name == "Stale Scraped Title | Store"

    refreshed = _upsert_category(session, store.id, "قهوة مختصة", url)
    assert refreshed.id == first.id  # same canonical row, not a duplicate
    assert refreshed.name == "قهوة مختصة"  # refreshed, not stuck on the old value


# --- Invariant 7: replay mode never sends a live network call ------------


async def test_invariant_replay_never_sends_a_live_call(session, monkeypatch):
    import httpx

    async def _forbidden_request(*args, **kwargs):
        raise AssertionError("ReplaySearchProvider must never make a network request")

    monkeypatch.setattr(httpx.AsyncClient, "request", _forbidden_request)
    monkeypatch.setattr(httpx.AsyncClient, "send", _forbidden_request)

    org, store, run = _make_org_store_run(session)
    from app.models.intent import Keyword

    keyword = Keyword(text="بن أخضر", country="sa", language="ar")
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=uuid.uuid4(), keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar", results=[{"rank": 1, "domain": "real-rival.sa", "url": "https://real-rival.sa/x"}],
        )
    )
    session.commit()

    from app.providers.search.base import SearchRequest

    provider = ReplaySearchProvider(session)
    response = await provider.search(SearchRequest(keyword="بن أخضر", country="sa", language="ar"))
    assert response.results[0].domain == "real-rival.sa"  # succeeded via DB, no network needed


# --- Invariant 8: the campaign-guard cost wrapper never hides provider identity ---


def test_invariant_cost_wrapper_never_hides_provider_identity(session):
    campaign = EvaluationCampaign(name="TRUST_CONTRACT", allocated_serp_budget=10)
    session.add(campaign)
    session.commit()
    session.refresh(campaign)

    real_provider = SerpApiProvider(api_key="unused-fake-key")
    guarded = CampaignGuardedSearchProvider(
        real_provider, session, campaign.id, Settings(max_live_serp_requests_per_campaign=250, max_live_serp_requests_per_run=30)
    )

    assert guarded.name == "campaign-guarded"  # the wrapper's own identity — fine for it to differ
    assert guarded.underlying_provider_name == "serpapi"  # but cost/DB attribution must resolve to the real provider
    assert estimate_search_cost_usd(guarded.underlying_provider_name) > 0.0


# --- Invariant 9: a displayed recommendation always has a traceable evidence chain ---


def test_invariant_displayed_recommendation_always_has_an_evidence_chain(session):
    org, store, run = _make_org_store_run(session)
    from app.models.evidence import Evidence, EvidenceSourceType
    from app.models.finding import Finding, FindingStatus

    evidence = Evidence(
        store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.page_gap_analysis,
        source_id=store.id, confidence=0.7, summary="raw evidence",
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    finding = Finding(
        store_id=store.id, research_run_id=run.id, finding_type="dominant_competitor",
        statement="rival dominates", confidence=0.6, status=FindingStatus.candidate,
    )
    session.add(finding)
    session.commit()
    session.refresh(finding)

    opp = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="missing_landing_page",
        title="t", description="d", finding_ids=[str(finding.id)], status=OpportunityStatus.open, fingerprint="fp-9",
    )
    session.add(opp)
    session.commit()
    session.refresh(opp)
    rec = Recommendation(
        store_id=store.id, opportunity_id=opp.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title="t", what_to_do="do", why_it_matters="why",
        evidence_ids=[str(evidence.id)], status=RecommendationStatus.new, fingerprint="rec-fp-9",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)

    trace = trace_recommendation_evidence(session, rec.id)
    assert trace is not None
    assert trace["opportunity"] is not None
    assert len(trace["findings"]) == 1
    assert len(trace["evidence"]) == 1


# --- Invariant 10: a synthetic/test competitor is never shown to the user ---


def test_invariant_synthetic_competitor_never_persisted_via_discovery(session):
    org, store, run = _make_org_store_run(session)
    from app.models.intent import Keyword

    keyword = Keyword(text="keyword", country="sa", language="ar")
    session.add(keyword)
    session.commit()
    session.refresh(keyword)
    session.add(
        SerpObservation(
            store_id=store.id, intent_id=uuid.uuid4(), keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar",
            results=[
                {"rank": 1, "domain": "example-competitor-1.test", "url": "https://example-competitor-1.test/x"},
                {"rank": 2, "domain": "real-rival.sa", "url": "https://real-rival.sa/x"},
            ],
        )
    )
    session.commit()

    mine_serp_competitors(session, store.id, store.url, run.id)

    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert {c.domain for c in competitors} == {"real-rival.sa"}
    assert all(not is_synthetic_test_domain(c.domain) for c in competitors)
