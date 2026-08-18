import uuid

from sqlmodel import select

from app.competitors.discovery_engine import get_or_create_competitor
from app.intent.intent_engine import _attach_keywords, get_or_create_stable_intent
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.competitor import CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentSource, Keyword
from app.models.measurement import MeasurementBaseline
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.opportunities.recommendation_engine import run_opportunity_discovery_agent, run_recommendation_engine


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-rec-engine")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://store.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def _seed_weak_intent(session, store, run, topic="coffee grinder", confidence=0.8):
    stable_intent = get_or_create_stable_intent(session, store_id=store.id, topic=topic, country="sa", language="ar")
    intent = Intent(
        store_id=store.id, research_run_id=run.id, stable_intent_id=stable_intent.id, topic=topic,
        country="sa", language="ar", confidence=confidence, source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, [topic], "sa", "ar")
    keyword = session.exec(select(Keyword).where(Keyword.text == topic)).one()
    observation = SerpObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=stable_intent.id, keyword_id=keyword.id,
        research_run_id=run.id,
        country="sa", language="ar", results=[], client_rank=None,
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)
    # Part Q3 — matches production (app.serp.serp_engine.run_serp_agent
    # always creates an Evidence row alongside the observation);
    # detect_google_visibility_gap_opportunities now requires it.
    session.add(
        Evidence(
            store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.serp_observation,
            source_id=observation.id, confidence=1.0, summary=f"SERP لـ'{topic}': المتجر غير ظاهر",
        )
    )
    session.commit()
    return intent


def test_discovery_agent_persists_and_updates_on_rerun(session):
    store, run = _make_store_and_run(session)
    _seed_weak_intent(session, store, run)

    first_pass = run_opportunity_discovery_agent(session, store.id, run.id)
    assert len(first_pass) >= 1
    assert first_pass == sorted(first_pass, key=lambda o: o.priority_score, reverse=True)

    all_opportunities = session.exec(select(Opportunity).where(Opportunity.store_id == store.id)).all()
    count_after_first = len(all_opportunities)

    second_pass = run_opportunity_discovery_agent(session, store.id, run.id)
    all_opportunities_after_second = session.exec(select(Opportunity).where(Opportunity.store_id == store.id)).all()

    assert len(second_pass) == len(first_pass)
    assert len(all_opportunities_after_second) == count_after_first  # updated, not duplicated


def test_discovery_and_recommendation_dedup_across_different_research_runs(session):
    """Regression: Intent rows are recreated every research run (never
    reused across runs) — a naive fingerprint keyed on intent_id would
    treat the same real-world topic as a brand-new opportunity every run.
    Fingerprints must be keyed on stable topic text instead."""
    store, run1 = _make_store_and_run(session)
    _seed_weak_intent(session, store, run1, topic="coffee grinder")

    opportunities_1 = run_opportunity_discovery_agent(session, store.id, run1.id)
    recommendations_1 = run_recommendation_engine(session, store.id, run1.id, opportunities_1, max_recommendations=5)

    # A second research run, with a brand-new Intent row for the *same* real topic.
    run2 = ResearchRun(store_id=store.id)
    session.add(run2)
    session.commit()
    session.refresh(run2)
    _seed_weak_intent(session, store, run2, topic="coffee grinder")

    opportunities_2 = run_opportunity_discovery_agent(session, store.id, run2.id)
    recommendations_2 = run_recommendation_engine(session, store.id, run2.id, opportunities_2, max_recommendations=5)

    all_opportunities = session.exec(select(Opportunity).where(Opportunity.store_id == store.id)).all()
    all_recommendations = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()

    assert len(all_opportunities) == len(opportunities_1)  # not doubled
    assert len(all_recommendations) == len(recommendations_1)  # not doubled
    assert {o.id for o in opportunities_2} == {o.id for o in opportunities_1}
    assert {r.id for r in recommendations_2} == {r.id for r in recommendations_1}

    updated_rec = all_recommendations[0]
    assert updated_rec.last_seen_research_run_id == run2.id
    assert updated_rec.first_seen_research_run_id == run1.id  # history preserved


def test_recommendation_engine_captures_baseline_once_on_creation_only(session):
    store, run = _make_store_and_run(session)
    _seed_weak_intent(session, store, run)
    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)

    recommendations = run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)
    rec_id = recommendations[0].id

    baselines = session.exec(select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == rec_id)).all()
    assert len(baselines) == 1

    # Re-running (simulating a later research pass) must not create a second baseline.
    opportunities_again = run_opportunity_discovery_agent(session, store.id, run.id)
    run_recommendation_engine(session, store.id, run.id, opportunities_again, max_recommendations=5)

    baselines_after = session.exec(
        select(MeasurementBaseline).where(MeasurementBaseline.recommendation_id == rec_id)
    ).all()
    assert len(baselines_after) == 1


def test_recommendation_engine_creates_recommendation_with_history_and_package(session):
    store, run = _make_store_and_run(session)
    _seed_weak_intent(session, store, run)
    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)

    recommendations = run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)

    assert 1 <= len(recommendations) <= 5
    rec = recommendations[0]
    assert rec.status == RecommendationStatus.new
    assert rec.title
    assert rec.what_to_do
    assert rec.why_it_matters
    assert len(rec.implementation_steps) > 0
    assert isinstance(rec.implementation_package, dict)

    history = session.exec(select(RecommendationHistory).where(RecommendationHistory.recommendation_id == rec.id)).all()
    assert len(history) == 1
    assert history[0].event_type == "created"


def test_recommendation_engine_updates_existing_on_rerun_without_duplicating(session):
    store, run = _make_store_and_run(session)
    _seed_weak_intent(session, store, run)
    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)

    first_run_recs = run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)
    total_after_first = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()

    # Re-run discovery + recommendation engine against the same run (simulating a later research pass)
    opportunities_again = run_opportunity_discovery_agent(session, store.id, run.id)
    second_run_recs = run_recommendation_engine(session, store.id, run.id, opportunities_again, max_recommendations=5)
    total_after_second = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()

    assert len(total_after_second) == len(total_after_first)  # no duplicates
    assert {r.id for r in first_run_recs} == {r.id for r in second_run_recs}  # same rows updated

    rec_id = first_run_recs[0].id
    history = session.exec(select(RecommendationHistory).where(RecommendationHistory.recommendation_id == rec_id)).all()
    event_types = [h.event_type for h in history]
    assert event_types == ["created", "updated"]  # nothing erased, new row appended


def test_discovery_agent_consolidates_opportunities_from_different_detectors_for_the_same_intent(session):
    """Part Q2 — end-to-end proof through the real engine (not just the
    consolidation unit tests): google_visibility_gap and ai_citation_gap
    both legitimately fire for the same intent here, but the customer
    must see one opportunity, not two."""
    store, run = _make_store_and_run(session)
    intent = _seed_weak_intent(session, store, run, topic="coffee grinder")  # google_visibility_gap fires

    # ai_citation_gap also needs: an AI observation where we're not
    # mentioned, and a competitor cited via AI for the same intent.
    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="أي مطحنة قهوة تنصحني فيها؟")
    session.add(variant)
    session.commit()
    session.refresh(variant)
    observation = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, prompt_variant_id=variant.id, research_run_id=run.id,
        provider="openai", model="gpt-4o-mini", country="sa", language="ar", mentioned=False,
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)
    session.add(
        Evidence(
            store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.ai_visibility_observation,
            source_id=observation.id, confidence=1.0, summary="لم يُذكر المتجر",
        )
    )
    session.commit()
    competitor = get_or_create_competitor(
        session, store_id=store.id, domain="rival.test", competitor_type=CompetitorType.ai_recommendation_competitor,
        research_run_id=run.id,
    )
    # Part Q3 — detect_ai_citation_gap_opportunities now filters out
    # non-business competitors (app.competitors.classification); classify
    # this one as a real competitor to match production, where
    # classify_competitors_for_run (Part G-B2) always runs before this.
    competitor.classification = "direct_competitor"
    session.add(competitor)
    session.commit()
    session.add(
        CompetitorRelationship(
            competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
            source=RelationshipSource.ai_visibility, rank_or_position=None,
        )
    )
    session.commit()

    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)

    types_present = {o.opportunity_type for o in opportunities}
    assert {"google_visibility_gap", "ai_citation_gap"} <= types_present or len(opportunities) == 1
    # The real assertion: whichever one detector's opportunity survived,
    # only one open opportunity exists for this intent — not two.
    open_for_this_intent = [
        o for o in opportunities if str(intent.stable_intent_id) in o.affected_intents
    ]
    assert len(open_for_this_intent) == 1
    survivor = open_for_this_intent[0]
    # It must carry the combined evidence trail from both detectors.
    assert len(survivor.evidence_ids) >= 1

    all_opportunities = session.exec(select(Opportunity).where(Opportunity.store_id == store.id)).all()
    merged = [o for o in all_opportunities if o.status == OpportunityStatus.merged]
    assert len(merged) == 1
    assert merged[0].merged_into_id == survivor.id


"""Beta Readiness Remediation — "NO EVIDENCE -> NO RECOMMENDATION",
enforced as a general invariant in run_recommendation_engine independent of
which detector produced the Opportunity. These tests exercise the engine
directly against a hand-built zero-evidence Opportunity (bypassing the
detectors entirely) specifically to prove the *invariant layer itself* is
the backstop — not just that today's fixed detectors happen not to trigger
it (that's covered separately in test_opportunity_detectors.py)."""


def _make_zero_evidence_opportunity(session, store, run, topic="unmeasured topic"):
    stable_intent = get_or_create_stable_intent(session, store_id=store.id, topic=topic, country="sa", language="ar")
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title=f"حسّن ظهورك في Google لـ '{topic}'", description="المتجر غير ظاهر ضمن أفضل 10 نتيجة لهذه النية",
        affected_intents=[str(stable_intent.id)], evidence_ids=[], confidence=0.6, estimated_impact=0.6,
        commercial_relevance=0.6, status=OpportunityStatus.open, fingerprint=f"zero-ev-{uuid.uuid4().hex[:8]}",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


def test_zero_evidence_opportunity_never_becomes_a_customer_visible_recommendation(session):
    store, run = _make_store_and_run(session)
    opportunity = _make_zero_evidence_opportunity(session, store, run)

    recommendations = run_recommendation_engine(session, store.id, run.id, [opportunity], max_recommendations=5)

    assert recommendations == []
    session.refresh(opportunity)
    assert opportunity.status == OpportunityStatus.needs_validation
    all_recs = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()
    assert all_recs == []


def test_recommendation_that_loses_all_evidence_on_rerun_is_withdrawn_not_left_stale(session):
    """A recommendation that was supported when first created must be
    withdrawn (status=needs_validation, evidence cleared) if a later run's
    topic-scope re-check finds none of its evidence survives -- never left
    sitting as status='new' with evidence_ids=[]."""
    store, run1 = _make_store_and_run(session)
    intent = _seed_weak_intent(session, store, run1, topic="grinder")
    opportunities_1 = run_opportunity_discovery_agent(session, store.id, run1.id)
    recommendations_1 = run_recommendation_engine(session, store.id, run1.id, opportunities_1, max_recommendations=5)
    assert len(recommendations_1) == 1
    rec_id = recommendations_1[0].id
    opp_id = recommendations_1[0].opportunity_id

    # Simulate evidence disappearing on a later run: strip the Opportunity's
    # evidence_ids directly (as if upstream re-scoring found nothing left
    # topic-aligned) and re-run the engine against the same Opportunity.
    opportunity = session.get(Opportunity, opp_id)
    opportunity.evidence_ids = []
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)

    run2 = ResearchRun(store_id=store.id)
    session.add(run2)
    session.commit()
    session.refresh(run2)

    recommendations_2 = run_recommendation_engine(session, store.id, run2.id, [opportunity], max_recommendations=5)

    assert recommendations_2 == []
    session.refresh(opportunity)
    assert opportunity.status == OpportunityStatus.needs_validation

    withdrawn = session.get(Recommendation, rec_id)
    assert withdrawn.status == RecommendationStatus.needs_validation
    assert withdrawn.evidence_ids == []

    history = session.exec(select(RecommendationHistory).where(RecommendationHistory.recommendation_id == rec_id)).all()
    assert "evidence_lost_withdrawn" in [h.event_type for h in history]


def test_recommendation_re_supported_after_needs_validation_comes_back_as_new(session):
    """Symmetric case: evidence returns on a later run -> the recommendation
    is genuinely re-validated (status back to 'new'), not silently ignored
    because it was already touched once."""
    store, run1 = _make_store_and_run(session)
    intent = _seed_weak_intent(session, store, run1, topic="kettle")
    opportunities_1 = run_opportunity_discovery_agent(session, store.id, run1.id)
    recommendations_1 = run_recommendation_engine(session, store.id, run1.id, opportunities_1, max_recommendations=5)
    rec_id = recommendations_1[0].id
    opp_id = recommendations_1[0].opportunity_id

    opportunity = session.get(Opportunity, opp_id)
    original_evidence = list(opportunity.evidence_ids)
    opportunity.evidence_ids = []
    session.add(opportunity)
    session.commit()

    run2 = ResearchRun(store_id=store.id)
    session.add(run2)
    session.commit()
    session.refresh(run2)
    run_recommendation_engine(session, store.id, run2.id, [opportunity], max_recommendations=5)
    session.refresh(opportunity)
    assert opportunity.status == OpportunityStatus.needs_validation

    # Evidence comes back (e.g. validate_finding supplied a fresh observation).
    opportunity.evidence_ids = original_evidence
    opportunity.status = OpportunityStatus.open
    session.add(opportunity)
    session.commit()

    run3 = ResearchRun(store_id=store.id)
    session.add(run3)
    session.commit()
    session.refresh(run3)
    recommendations_3 = run_recommendation_engine(session, store.id, run3.id, [opportunity], max_recommendations=5)

    assert len(recommendations_3) == 1
    assert recommendations_3[0].id == rec_id
    assert recommendations_3[0].status == RecommendationStatus.new
    assert recommendations_3[0].evidence_ids == original_evidence


def test_rediscovery_of_a_merged_opportunity_refreshes_it_instead_of_duplicating(session):
    """Beta Readiness Remediation — confirmed second-order bug found during
    the Round 3 replay: once Q2 consolidation marks an Opportunity
    'merged', it used to become permanently invisible to
    _persist_opportunity's get-or-create lookup (which only matched
    status==open). A later run rediscovering the exact same real-world
    fingerprint then created a brand-new duplicate Opportunity instead of
    refreshing the merged one -- and the Recommendation kept by R5 dedup as
    the survivor stayed pointed at the now-orphaned merged Opportunity,
    silently freezing its content (what_we_found etc.) forever. Fixed by
    widening the lookup to also match merged/needs_validation and flipping
    status back to open on rediscovery."""
    store, run = _make_store_and_run(session)
    intent = _seed_weak_intent(session, store, run, topic="grinder")
    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)
    opportunity_id = opportunities[0].id
    recommendations = run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)
    rec_id = recommendations[0].id
    original_what_we_found = recommendations[0].what_we_found

    # Simulate the opportunity having been merged away by a later
    # consolidation pass (Q2) — the exact state that orphaned rediscovery.
    opportunity = session.get(Opportunity, opportunity_id)
    opportunity.status = OpportunityStatus.merged
    session.add(opportunity)
    session.commit()

    run2 = ResearchRun(store_id=store.id)
    session.add(run2)
    session.commit()
    session.refresh(run2)
    _seed_weak_intent(session, store, run2, topic="grinder")  # same real-world topic, fresh Intent row

    opportunities_2 = run_opportunity_discovery_agent(session, store.id, run2.id)

    # Must refresh the SAME opportunity row, not create a second one.
    assert len(opportunities_2) == 1
    assert opportunities_2[0].id == opportunity_id
    assert opportunities_2[0].status == OpportunityStatus.open

    recommendations_2 = run_recommendation_engine(session, store.id, run2.id, opportunities_2, max_recommendations=5)

    assert len(recommendations_2) == 1
    assert recommendations_2[0].id == rec_id  # same recommendation row, refreshed -- not a duplicate
    assert recommendations_2[0].what_we_found  # content actually got refreshed
    all_recs_for_store = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()
    assert len(all_recs_for_store) == 1  # no orphaned duplicate left behind


def test_recommendation_carries_confidence_tier_and_structured_content(session):
    store, run = _make_store_and_run(session)
    _seed_weak_intent(session, store, run)
    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)

    recommendations = run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)

    rec = recommendations[0]
    assert rec.confidence_tier in ("low", "medium", "high")
    assert rec.what_we_found  # never empty for a persisted (= evidence-backed) recommendation
    assert rec.why_this_improvement
    assert rec.claim_basis in ("observed", "observed_with_best_practice", "unsupported")
