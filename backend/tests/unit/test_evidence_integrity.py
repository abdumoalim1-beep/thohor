import uuid

from sqlmodel import select

from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentSource
from app.models.intent_cluster import IntentCluster
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.org import Organization
from app.models.recommendation import Recommendation, RecommendationHistory, RecommendationStatus
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.opportunities.dedup import consolidate_duplicate_recommendations
from app.opportunities.evidence_integrity import check_evidence_scope
from app.opportunities.recommendation_engine import run_recommendation_engine

"""Part R2-F4 — Evidence Scope Integrity. Confirmed root cause (traced via
direct DB inspection on jarir.com, recommendation dc804982-a6ec-4aee-900d-
db96bd7e757c): Part R5's semantic dedup can judge product-specific
google_visibility_gap recommendations for genuinely different products
(Apple/Roku/Ring/Microsoft) as duplicates purely because they share a
near-identical action-template sentence and land in the same broad Q1
intent cluster, then blindly unions their evidence into the survivor. These
tests reproduce that exact real-world pattern and prove the fix."""


def _make_store_and_run(session):
    org = Organization(name="t", slug=f"t-evint-{uuid.uuid4().hex[:8]}")
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


def _make_intent_with_serp_evidence(session, store, run, *, topic, category="إلكترونيات"):
    """Mirrors the real pipeline shape: one Intent -> one SerpObservation ->
    one serp_observation Evidence row, exactly what
    detect_google_visibility_gap_opportunities builds evidence_ids from."""
    intent = Intent(
        store_id=store.id, research_run_id=run.id, stable_intent_id=uuid.uuid4(), topic=topic,
        category=category, country="sa", language="ar", confidence=0.8,
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)

    observation = SerpObservation(
        store_id=store.id, intent_id=intent.id, stable_intent_id=intent.stable_intent_id, keyword_id=uuid.uuid4(),
        research_run_id=run.id, country="sa", language="ar", results=[], client_rank=None,
    )
    session.add(observation)
    session.commit()
    session.refresh(observation)

    evidence = Evidence(
        store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.serp_observation,
        source_id=observation.id, confidence=1.0, summary=f"SERP لـ'{topic}': المتجر غير ظاهر ضمن أفضل 10 نتيجة",
    )
    session.add(evidence)
    session.commit()
    session.refresh(evidence)
    return intent, evidence


# --- check_evidence_scope: pure-ish (DB-backed) unit tests ------------------


def test_evidence_matching_target_topic_is_aligned(session):
    store, run = _make_store_and_run(session)
    _, evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات أبل")

    result = check_evidence_scope(session, "منتجات أبل", [str(evidence.id)])

    assert result.aligned_evidence_ids == [str(evidence.id)]
    assert result.dropped_evidence_ids == []
    assert result.scope_score == 1.0


def test_evidence_about_a_different_topic_is_dropped(session):
    store, run = _make_store_and_run(session)
    _, roku_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات روكو")

    result = check_evidence_scope(session, "منتجات أبل", [str(roku_evidence.id)])

    assert result.aligned_evidence_ids == []
    assert result.dropped_evidence_ids == [str(roku_evidence.id)]
    assert result.scope_score == 0.0


def test_evidence_mix_of_matching_and_unrelated_computes_partial_scope_score(session):
    store, run = _make_store_and_run(session)
    _, apple_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات أبل")
    _, roku_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات روكو")
    _, ring_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات رينغ")

    result = check_evidence_scope(
        session, "منتجات أبل", [str(apple_evidence.id), str(roku_evidence.id), str(ring_evidence.id)]
    )

    assert result.aligned_evidence_ids == [str(apple_evidence.id)]
    assert set(result.dropped_evidence_ids) == {str(roku_evidence.id), str(ring_evidence.id)}
    assert abs(result.scope_score - (1 / 3)) < 1e-9


def test_evidence_sharing_only_a_broad_category_is_not_enough_to_align(session):
    """The exact jarir.com failure mode: 'منتجات أبل' and 'منتجات روكو' share
    the category 'إلكترونيات' but are different products — category overlap
    alone must not be treated as topic alignment, or this check would be
    just as coarse as the Q1 cluster that caused the bug."""
    store, run = _make_store_and_run(session)
    _, roku_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات روكو", category="إلكترونيات")

    result = check_evidence_scope(session, "منتجات أبل", [str(roku_evidence.id)])

    assert result.aligned_evidence_ids == []


def test_unresolvable_evidence_ids_are_kept_not_penalized(session):
    """Evidence rows the check can't structurally resolve to an intent
    (bad UUIDs, or a row that doesn't exist) must never be silently
    dropped -- this check only narrows scope for evidence it can positively
    verify is off-topic."""
    result = check_evidence_scope(session, "منتجات أبل", ["not-a-uuid", str(uuid.uuid4())])

    assert result.aligned_evidence_ids == ["not-a-uuid"]
    assert len(result.dropped_evidence_ids) == 1  # the well-formed but nonexistent row


def test_empty_evidence_list_has_perfect_scope_score(session):
    result = check_evidence_scope(session, "منتجات أبل", [])
    assert result.aligned_evidence_ids == []
    assert result.scope_score == 1.0


# --- dedup.py: merge must never widen evidence scope to an unrelated topic -


def _make_opportunity(session, store, run, *, fingerprint_target, affected_intents, evidence_ids, priority_score):
    # fingerprint_target is a transient OpportunityDraft-only concept (see
    # detectors.py) -- the persisted Opportunity row has no such column;
    # the recommendation/dedup code under test resolves the target topic
    # structurally from affected_intents instead (target_topic_from_intents).
    opportunity = Opportunity(
        store_id=store.id, research_run_id=run.id, opportunity_type="google_visibility_gap",
        title=f"حسّن ظهورك في Google لـ '{fingerprint_target}'", description="d",
        affected_intents=affected_intents, evidence_ids=evidence_ids, confidence=0.6,
        priority_score=priority_score,
        status=OpportunityStatus.open, fingerprint=f"fp-{uuid.uuid4()}",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


def _make_recommendation(session, store, run, opportunity, *, what_to_do, priority_score):
    rec = Recommendation(
        store_id=store.id, opportunity_id=opportunity.id, first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id, title=opportunity.title, what_to_do=what_to_do, why_it_matters="w",
        target_intents=opportunity.affected_intents, evidence_ids=opportunity.evidence_ids,
        priority_score=priority_score, status=RecommendationStatus.new, fingerprint=f"fp-{uuid.uuid4()}",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def test_dedup_merge_of_clustered_product_recommendations_does_not_leak_unrelated_evidence(session):
    """Reproduces the confirmed jarir.com bug end-to-end at the dedup layer:
    five product-specific recommendations (Apple/Roku/Ring/Microsoft/generic
    tech) share an intent cluster and an almost-identical action template,
    so R5's is_semantic_duplicate legitimately groups them (that judgment
    is out of scope for this fix, per the phase rule to preserve R1-R8).
    What must change is that the survivor (Apple, highest priority, with no
    evidence of its own -- matching the real data) must NOT end up carrying
    the Roku/Ring/Microsoft evidence after the merge."""
    store, run = _make_store_and_run(session)
    cluster = IntentCluster(store_id=store.id, research_run_id=run.id, label="إلكترونيات", intent_count=5)
    session.add(cluster)
    session.commit()
    session.refresh(cluster)

    def _clustered_intent(topic):
        intent, evidence = _make_intent_with_serp_evidence(session, store, run, topic=topic)
        intent.cluster_id = cluster.id
        session.add(intent)
        session.commit()
        return intent, evidence

    apple_intent, _ = _clustered_intent("منتجات أبل")
    roku_intent, roku_evidence = _clustered_intent("منتجات روكو")
    ring_intent, ring_evidence = _clustered_intent("منتجات رينغ")
    ms_intent, ms_evidence = _clustered_intent("منتجات مايكروسوفت")

    same_action = "راجع الصفحة الأنسب لنية '{}' وحسّن العنوان/الوصف/المحتوى ليطابق ما يبحث عنه العملاء فعليًا."

    apple_opp = _make_opportunity(
        session, store, run, fingerprint_target="منتجات أبل", affected_intents=[str(apple_intent.stable_intent_id)],
        evidence_ids=[], priority_score=59.5,
    )
    roku_opp = _make_opportunity(
        session, store, run, fingerprint_target="منتجات روكو", affected_intents=[str(roku_intent.stable_intent_id)],
        evidence_ids=[str(roku_evidence.id)], priority_score=40.8,
    )
    ring_opp = _make_opportunity(
        session, store, run, fingerprint_target="منتجات رينغ", affected_intents=[str(ring_intent.stable_intent_id)],
        evidence_ids=[str(ring_evidence.id)], priority_score=40.8,
    )
    ms_opp = _make_opportunity(
        session, store, run, fingerprint_target="منتجات مايكروسوفت", affected_intents=[str(ms_intent.stable_intent_id)],
        evidence_ids=[str(ms_evidence.id)], priority_score=50.2,
    )

    apple_rec = _make_recommendation(session, store, run, apple_opp, what_to_do=same_action.format("منتجات أبل"), priority_score=59.5)
    _make_recommendation(session, store, run, roku_opp, what_to_do=same_action.format("منتجات روكو"), priority_score=40.8)
    _make_recommendation(session, store, run, ring_opp, what_to_do=same_action.format("منتجات رينغ"), priority_score=40.8)
    _make_recommendation(session, store, run, ms_opp, what_to_do=same_action.format("منتجات مايكروسوفت"), priority_score=50.2)

    survivors = consolidate_duplicate_recommendations(session, store.id, run.id)

    assert len(survivors) == 1
    survivor = survivors[0]
    assert survivor.id == apple_rec.id
    # The bug: before the fix this would equal [roku, ring, ms] evidence.
    assert survivor.evidence_ids == []


# --- recommendation_engine.py: never create a recommendation whose only ----
# --- evidence is provably about a different topic ---------------------------


def test_recommendation_not_generated_when_opportunity_evidence_is_entirely_out_of_scope(session):
    """Explicit regression test required by the Round 2 remediation
    directive: an 'Apple products' opportunity backed only by Roku/Ring
    evidence (e.g. corrupted upstream by some other merge path) must not
    produce a recommendation at all."""
    store, run = _make_store_and_run(session)
    apple_intent = Intent(
        store_id=store.id, research_run_id=run.id, stable_intent_id=uuid.uuid4(), topic="منتجات أبل",
        category="إلكترونيات", country="sa", language="ar", confidence=0.8,
        source=IntentSource.deterministic_catalog,
    )
    session.add(apple_intent)
    session.commit()
    session.refresh(apple_intent)
    _, roku_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات روكو")
    _, ring_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات رينغ")

    corrupted_opportunity = _make_opportunity(
        session, store, run, fingerprint_target="منتجات أبل", affected_intents=[str(apple_intent.stable_intent_id)],
        evidence_ids=[str(roku_evidence.id), str(ring_evidence.id)], priority_score=59.5,
    )

    created = run_recommendation_engine(session, store.id, run.id, [corrupted_opportunity], max_recommendations=5)

    assert created == []
    all_recs = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()
    assert all_recs == []


def test_recommendation_is_generated_normally_when_evidence_matches_its_own_topic(session):
    """Sanity check: the integrity gate must not block the normal, correct
    case where evidence genuinely supports the opportunity's own topic."""
    store, run = _make_store_and_run(session)
    apple_intent, apple_evidence = _make_intent_with_serp_evidence(session, store, run, topic="منتجات أبل")

    opportunity = _make_opportunity(
        session, store, run, fingerprint_target="منتجات أبل", affected_intents=[str(apple_intent.stable_intent_id)],
        evidence_ids=[str(apple_evidence.id)], priority_score=59.5,
    )

    created = run_recommendation_engine(session, store.id, run.id, [opportunity], max_recommendations=5)

    assert len(created) == 1
    assert created[0].evidence_ids == [str(apple_evidence.id)]
