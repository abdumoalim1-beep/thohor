from sqlmodel import select

from app.intent.intent_engine import _attach_keywords
from app.models.ai_visibility import AIVisibilityObservation
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.finding import Finding, FindingStatus
from app.models.intent import Intent, IntentSource, Keyword
from app.models.org import Organization
from app.models.page_intelligence import PageGapAnalysis
from app.models.stable_intent import StableIntent
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.opportunities.detectors import (
    detect_ai_citation_gap_opportunities,
    detect_category_visibility_gap_opportunities,
    detect_google_visibility_gap_opportunities,
    detect_missing_landing_page_opportunities,
)


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-opp-detectors")
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


def _make_intent(session, store, run, topic, category=None, confidence=0.8):
    stable_intent = StableIntent(
        store_id=store.id, canonical_topic=topic, normalized_topic=topic.lower(), country="sa", language="ar",
        locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)

    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        stable_intent_id=stable_intent.id,
        topic=topic,
        category=category,
        country="sa",
        language="ar",
        confidence=confidence,
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    return intent


def _make_competitor(
    session, store, run, domain, competitor_type=CompetitorType.search_competitor, classification="direct_competitor"
):
    # Part Q3 — classification defaults to "direct_competitor" (a real
    # business competitor) since that's the realistic case most of these
    # tests exercise; detectors now filter out anything else (see
    # app.competitors.classification.is_business_competitor), so a test
    # specifically proving that filter passes classification="marketplace"
    # (or similar) explicitly.
    competitor = Competitor(
        store_id=store.id, domain=domain, name=domain, competitor_type=competitor_type,
        first_seen_research_run_id=run.id, classification=classification,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor


def test_detect_missing_landing_page_from_page_gap_analysis(session):
    store, run = _make_store_and_run(session)
    intent = _make_intent(session, store, run, "coffee grinder")
    competitor = _make_competitor(session, store, run, "rival.test")

    analysis = PageGapAnalysis(
        store_id=store.id, intent_id=intent.id, competitor_id=competitor.id, research_run_id=run.id,
        competitor_url="https://rival.test/grinders", gaps=["missing buying guide"],
        recommendation_summary="أضف دليل شراء.", confidence=0.7,
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)

    evidence = Evidence(
        store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.page_gap_analysis,
        source_id=analysis.id, confidence=0.7, summary="gap evidence",
    )
    session.add(evidence)
    session.commit()

    drafts = detect_missing_landing_page_opportunities(session, store.id, run.id)

    assert len(drafts) == 1
    draft = drafts[0]
    assert draft.opportunity_type == "missing_landing_page"
    assert draft.affected_intents == [str(intent.stable_intent_id)]
    assert draft.competitors == [str(competitor.id)]
    assert len(draft.evidence_ids) == 1
    assert draft.confidence == 0.7


def test_detect_missing_landing_page_skips_irrelevant_competitor(session):
    """Part Q3 — a marketplace/directory beating us in SERP for an intent
    is not a real business competitor; must never surface as 'you're
    losing to X'."""
    store, run = _make_store_and_run(session)
    intent = _make_intent(session, store, run, "coffee grinder")
    marketplace = _make_competitor(session, store, run, "amazon.test", classification="marketplace")

    analysis = PageGapAnalysis(
        store_id=store.id, intent_id=intent.id, competitor_id=marketplace.id, research_run_id=run.id,
        competitor_url="https://amazon.test/grinders", gaps=["missing buying guide"],
        recommendation_summary="أضف دليل شراء.", confidence=0.7,
    )
    session.add(analysis)
    session.commit()

    drafts = detect_missing_landing_page_opportunities(session, store.id, run.id)

    assert drafts == []


def test_detect_google_visibility_gap_flags_confirmed_absent_and_weak_intents(session):
    """Beta Readiness Remediation (Round 3 P0 fix): an intent with NO
    SerpObservation at all this run must never be flagged — that means we
    simply never queried it, not that we confirmed it absent. An intent
    WITH a SerpObservation whose client_rank is None (queried, store not
    found in the results) is a real, evidence-backed negative result and
    must still be flagged with a real evidence_id attached."""
    store, run = _make_store_and_run(session)
    confirmed_absent = _make_intent(session, store, run, "confirmed absent topic", confidence=0.7)
    never_queried = _make_intent(session, store, run, "never queried topic", confidence=0.7)
    weak = _make_intent(session, store, run, "weak topic", confidence=0.6)
    strong = _make_intent(session, store, run, "strong topic", confidence=0.9)
    low_confidence = _make_intent(session, store, run, "low confidence topic", confidence=0.1)

    # never_queried intentionally gets no SerpObservation row at all.
    for intent, rank in [(confirmed_absent, None), (weak, 15), (strong, 3), (low_confidence, None)]:
        _attach_keywords(session, intent, [intent.topic], "sa", "ar")
        keyword = session.exec(select(Keyword).where(Keyword.text == intent.topic)).one()
        observation = SerpObservation(
            store_id=store.id, intent_id=intent.id, keyword_id=keyword.id, research_run_id=run.id,
            country="sa", language="ar", results=[], client_rank=rank,
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)
        # A real serp_agent_run always creates the backing Evidence row
        # alongside the SerpObservation (app.serp.serp_engine) — replicated
        # here so _evidence_ids_for has something real to find.
        session.add(
            Evidence(
                store_id=store.id, research_run_id=run.id,
                source_type=EvidenceSourceType.serp_observation, source_id=observation.id,
                confidence=0.9, summary=f"serp observation for {intent.topic}",
            )
        )
    session.commit()

    drafts = detect_google_visibility_gap_opportunities(session, store.id, run.id)
    flagged_intent_ids = {d.affected_intents[0] for d in drafts}
    drafts_by_intent = {d.affected_intents[0]: d for d in drafts}

    assert str(confirmed_absent.stable_intent_id) in flagged_intent_ids
    assert drafts_by_intent[str(confirmed_absent.stable_intent_id)].evidence_ids  # real evidence, not []
    assert str(never_queried.stable_intent_id) not in flagged_intent_ids  # no data -> no claim, no opportunity
    assert str(weak.stable_intent_id) in flagged_intent_ids
    assert str(strong.stable_intent_id) not in flagged_intent_ids
    assert str(low_confidence.stable_intent_id) not in flagged_intent_ids  # below MIN_INTENT_CONFIDENCE


def test_detect_ai_citation_gap_requires_both_absence_and_competitor_citation(session):
    store, run = _make_store_and_run(session)
    gap_intent = _make_intent(session, store, run, "gap topic")
    mentioned_intent = _make_intent(session, store, run, "mentioned topic")
    no_competitor_intent = _make_intent(session, store, run, "no competitor topic")

    competitor = _make_competitor(session, store, run, "rival.test", CompetitorType.ai_recommendation_competitor)

    for intent, mentioned in [(gap_intent, False), (mentioned_intent, True), (no_competitor_intent, False)]:
        obs = AIVisibilityObservation(
            store_id=store.id, intent_id=intent.id, prompt_variant_id=intent.id,  # placeholder FK, unenforced in sqlite
            research_run_id=run.id, provider="openai", model="gpt-4o-mini", country="sa", language="ar",
            mentioned=mentioned,
        )
        session.add(obs)
        session.commit()
        session.refresh(obs)
        session.add(
            Evidence(
                store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.ai_visibility_observation,
                source_id=obs.id, confidence=1.0, summary="ai obs evidence",
            )
        )
    session.commit()

    for intent in (gap_intent, mentioned_intent):
        session.add(
            CompetitorRelationship(
                competitor_id=competitor.id, intent_id=intent.id, research_run_id=run.id,
                source=RelationshipSource.ai_visibility, rank_or_position=1,
            )
        )
    session.commit()

    drafts = detect_ai_citation_gap_opportunities(session, store.id, run.id)
    flagged_intent_ids = {d.affected_intents[0] for d in drafts}

    assert str(gap_intent.stable_intent_id) in flagged_intent_ids
    assert str(mentioned_intent.stable_intent_id) not in flagged_intent_ids  # was mentioned -> no gap
    assert str(no_competitor_intent.stable_intent_id) not in flagged_intent_ids  # no competitor citation -> no gap
    gap_draft = next(d for d in drafts if d.affected_intents[0] == str(gap_intent.stable_intent_id))
    assert len(gap_draft.evidence_ids) == 1


def test_detect_ai_citation_gap_skips_when_only_irrelevant_competitors_are_cited(session):
    """Part Q3 — an AI answer citing a marketplace/social page (not a real
    competitor) alongside our absence must never surface as an ai_citation_gap."""
    store, run = _make_store_and_run(session)
    intent = _make_intent(session, store, run, "gap topic")
    marketplace = _make_competitor(
        session, store, run, "amazon.test", CompetitorType.ai_recommendation_competitor, classification="marketplace",
    )

    obs = AIVisibilityObservation(
        store_id=store.id, intent_id=intent.id, prompt_variant_id=intent.id,
        research_run_id=run.id, provider="openai", model="gpt-4o-mini", country="sa", language="ar", mentioned=False,
    )
    session.add(obs)
    session.commit()
    session.refresh(obs)
    session.add(
        Evidence(
            store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.ai_visibility_observation,
            source_id=obs.id, confidence=1.0, summary="ai obs evidence",
        )
    )
    session.add(
        CompetitorRelationship(
            competitor_id=marketplace.id, intent_id=intent.id, research_run_id=run.id,
            source=RelationshipSource.ai_visibility, rank_or_position=1,
        )
    )
    session.commit()

    drafts = detect_ai_citation_gap_opportunities(session, store.id, run.id)

    assert drafts == []


def test_detect_category_visibility_gap_flags_weak_categories_only(session):
    store, run = _make_store_and_run(session)
    weak1 = _make_intent(session, store, run, "weak1", category="أدوات القهوة")
    weak2 = _make_intent(session, store, run, "weak2", category="أدوات القهوة")
    strong1 = _make_intent(session, store, run, "strong1", category="محاصيل القهوة")
    strong2 = _make_intent(session, store, run, "strong2", category="محاصيل القهوة")
    single = _make_intent(session, store, run, "single", category="فئة منفردة")

    for intent, rank in [(weak1, None), (weak2, None), (strong1, 1), (strong2, 2), (single, None)]:
        _attach_keywords(session, intent, [intent.topic], "sa", "ar")
        keyword = session.exec(select(Keyword).where(Keyword.text == intent.topic)).one()
        session.add(
            SerpObservation(
                store_id=store.id, intent_id=intent.id, keyword_id=keyword.id, research_run_id=run.id,
                country="sa", language="ar", results=[], client_rank=rank,
            )
        )
    session.commit()

    drafts = detect_category_visibility_gap_opportunities(session, store.id, run.id)
    flagged_categories = {d.fingerprint_target for d in drafts}

    assert "أدوات القهوة" in flagged_categories
    assert "محاصيل القهوة" not in flagged_categories
    assert "فئة منفردة" not in flagged_categories  # below MIN_CATEGORY_INTENTS
