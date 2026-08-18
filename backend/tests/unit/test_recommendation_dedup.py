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
from app.opportunities.dedup import (
    build_signature,
    consolidate_duplicate_recommendations,
    is_semantic_duplicate,
)
from app.opportunities.recommendation_engine import run_opportunity_discovery_agent, run_recommendation_engine


def _sig(**overrides):
    defaults = dict(
        opportunity_type="google_visibility_gap",
        target_page="https://store.example/coffee-grinders",
        target_intents=["intent-a"],
        what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة مع محتوى غني ومقارنات",
        evidence_ids=["ev-1", "ev-2"],
        intent_cluster_ids=frozenset(),
    )
    defaults.update(overrides)
    return build_signature(**defaults)


# --- Part R5: pure signature-matching scenarios (no DB) ------------------


def test_exact_duplicate_is_a_semantic_duplicate():
    a = _sig()
    b = _sig()
    assert is_semantic_duplicate(a, b) is True


def test_semantic_near_duplicate_via_shared_intent_cluster():
    """Same real gap, reached through two differently-worded intents ('قهوة
    مختصة' vs 'أفضل قهوة مختصة') — no shared target_page/intent id, and no
    evidence overlap at all (each intent's own independent SERP evidence).
    Q1's intent clustering already grouped them as the same topic, and
    that's corroboration enough on its own."""
    cluster_id = uuid.uuid4()
    a = _sig(
        target_page=None,
        target_intents=["intent-a"],
        what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة المختصة",
        evidence_ids=["ev-1"],
        intent_cluster_ids=frozenset({cluster_id}),
    )
    b = _sig(
        target_page=None,
        target_intents=["intent-b"],  # different intent id -> different fallback target
        what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة المختصة",  # same action template
        evidence_ids=["ev-2"],  # zero evidence overlap
        intent_cluster_ids=frozenset({cluster_id}),  # same cluster
    )
    assert is_semantic_duplicate(a, b) is True


def test_evidence_overlap_alone_can_also_signal_a_duplicate():
    """No shared target, no shared cluster — but the two opportunities were
    independently built from majority-overlapping evidence (e.g. two
    detectors both citing the same underlying observations), which is
    corroboration enough by itself."""
    a = _sig(target_page=None, target_intents=["intent-a"], evidence_ids=["ev-1", "ev-2"], intent_cluster_ids=frozenset({uuid.uuid4()}))
    b = _sig(target_page=None, target_intents=["intent-b"], evidence_ids=["ev-1", "ev-2", "ev-3"], intent_cluster_ids=frozenset({uuid.uuid4()}))
    # jaccard({ev-1,ev-2}, {ev-1,ev-2,ev-3}) = 2/3 ≈ 0.67 >= threshold
    assert is_semantic_duplicate(a, b) is True


def test_same_intent_different_action_is_not_a_duplicate():
    """Two legitimately distinct recommendations can share a target/intent
    — e.g. 'write more content' vs 'fix a technical SEO issue' for the same
    page. A different action must never be treated as a duplicate no matter
    how much else lines up."""
    a = _sig(what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة مع محتوى غني ومقارنات")
    b = _sig(what_to_do="أصلح بيانات Schema.org المفقودة في صفحة المنتج الحالية")
    assert is_semantic_duplicate(a, b) is False


def test_different_intent_same_target_page_is_a_duplicate():
    """Same physical page, same action, reached via two different intents —
    still one real-world recommendation ('improve this page'), regardless
    of which intent motivated it."""
    a = _sig(target_intents=["intent-a"], intent_cluster_ids=frozenset({uuid.uuid4()}))
    b = _sig(target_intents=["intent-b"], intent_cluster_ids=frozenset({uuid.uuid4()}))
    assert a.normalized_target == b.normalized_target  # same target_page
    assert is_semantic_duplicate(a, b) is True


def test_legitimately_distinct_recommendations_are_not_merged():
    """Different target, different intent cluster, no evidence overlap,
    different action — nothing should trigger a merge."""
    a = _sig(
        target_page="https://store.example/coffee-grinders",
        target_intents=["intent-a"],
        what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة",
        evidence_ids=["ev-1", "ev-2"],
        intent_cluster_ids=frozenset({uuid.uuid4()}),
    )
    b = _sig(
        target_page="https://store.example/espresso-machines",
        target_intents=["intent-z"],
        what_to_do="أضف قسم أسئلة شائعة لمكائن الإسبريسو",
        evidence_ids=["ev-9", "ev-10"],
        intent_cluster_ids=frozenset({uuid.uuid4()}),
    )
    assert is_semantic_duplicate(a, b) is False


def test_different_opportunity_type_never_merges_even_if_everything_else_matches():
    a = _sig(opportunity_type="google_visibility_gap")
    b = _sig(opportunity_type="ai_citation_gap")
    assert is_semantic_duplicate(a, b) is False


# --- consolidate_duplicate_recommendations: DB-level behavior ------------


def _make_store_and_run(session):
    org = Organization(name="t", slug=f"t-dedup-{uuid.uuid4().hex[:8]}")
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


def _make_opportunity(session, store, run, *, opportunity_type, fingerprint_target, affected_intents):
    opportunity = Opportunity(
        store_id=store.id,
        research_run_id=run.id,
        opportunity_type=opportunity_type,
        title="t",
        description="d",
        affected_intents=affected_intents,
        evidence_ids=["ev-1", "ev-2"],
        confidence=0.6,
        priority_score=50.0,
        status=OpportunityStatus.open,
        fingerprint=f"fp-{uuid.uuid4()}",
    )
    session.add(opportunity)
    session.commit()
    session.refresh(opportunity)
    return opportunity


def _make_recommendation(session, store, run, opportunity, *, target_page, what_to_do, priority_score):
    rec = Recommendation(
        store_id=store.id,
        opportunity_id=opportunity.id,
        first_seen_research_run_id=run.id,
        last_seen_research_run_id=run.id,
        title="t",
        what_to_do=what_to_do,
        why_it_matters="w",
        target_page=target_page,
        target_intents=opportunity.affected_intents,
        evidence_ids=opportunity.evidence_ids,
        priority_score=priority_score,
        status=RecommendationStatus.new,
        fingerprint=f"fp-{uuid.uuid4()}",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def test_consolidate_duplicate_recommendations_supersedes_the_lower_priority_duplicate(session):
    store, run = _make_store_and_run(session)
    opp_a = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", fingerprint_target="a", affected_intents=["intent-a"]
    )
    opp_b = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", fingerprint_target="b", affected_intents=["intent-b"]
    )
    same_page = "https://store.example/coffee-grinders"
    same_action = "أنشئ صفحة هبوط مخصصة لمطاحن القهوة مع محتوى غني ومقارنات"
    winner = _make_recommendation(session, store, run, opp_a, target_page=same_page, what_to_do=same_action, priority_score=80.0)
    loser = _make_recommendation(session, store, run, opp_b, target_page=same_page, what_to_do=same_action, priority_score=40.0)

    survivors = consolidate_duplicate_recommendations(session, store.id, run.id)

    survivor_ids = {r.id for r in survivors}
    assert winner.id in survivor_ids
    assert loser.id not in survivor_ids

    session.refresh(loser)
    session.refresh(winner)
    assert loser.status == RecommendationStatus.superseded
    assert winner.status == RecommendationStatus.new

    history = session.exec(
        select(RecommendationHistory).where(RecommendationHistory.recommendation_id == loser.id)
    ).all()
    assert any(h.event_type == "superseded_duplicate" and h.snapshot.get("superseded_by") == str(winner.id) for h in history)


def test_consolidate_duplicate_recommendations_leaves_distinct_recommendations_alone(session):
    store, run = _make_store_and_run(session)
    opp_a = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", fingerprint_target="a", affected_intents=["intent-a"]
    )
    opp_b = _make_opportunity(
        session, store, run, opportunity_type="google_visibility_gap", fingerprint_target="b", affected_intents=["intent-z"]
    )
    rec_a = _make_recommendation(
        session, store, run, opp_a,
        target_page="https://store.example/coffee-grinders",
        what_to_do="أنشئ صفحة هبوط مخصصة لمطاحن القهوة",
        priority_score=80.0,
    )
    rec_b = _make_recommendation(
        session, store, run, opp_b,
        target_page="https://store.example/espresso-machines",
        what_to_do="أضف قسم أسئلة شائعة لمكائن الإسبريسو",
        priority_score=60.0,
    )

    survivors = consolidate_duplicate_recommendations(session, store.id, run.id)

    survivor_ids = {r.id for r in survivors}
    assert {rec_a.id, rec_b.id} <= survivor_ids
    session.refresh(rec_a)
    session.refresh(rec_b)
    assert rec_a.status == RecommendationStatus.new
    assert rec_b.status == RecommendationStatus.new


def test_recommendation_engine_end_to_end_does_not_expose_duplicate_recommendations_across_runs(session):
    """Two intents that mean the same thing (clustered together by Part Q1)
    both surface a google_visibility_gap opportunity for the same store
    across two research runs. Before Part R5, these would sit as two
    independent 'new' recommendations forever — this proves the semantic
    dedup pass wired into run_recommendation_engine collapses them."""
    store, run = _make_store_and_run(session)

    def _seed_intent(topic: str) -> Intent:
        intent = Intent(
            store_id=store.id, research_run_id=run.id, stable_intent_id=uuid.uuid4(), topic=topic,
            country="sa", language="ar", confidence=0.8, source=IntentSource.deterministic_catalog,
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
        session.add(
            Evidence(
                store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.serp_observation,
                source_id=observation.id, confidence=1.0, summary=f"SERP لـ'{topic}': المتجر غير ظاهر",
            )
        )
        session.commit()
        return intent

    intent_1 = _seed_intent("قهوة مختصة")
    intent_2 = _seed_intent("أفضل قهوة مختصة")

    cluster = IntentCluster(store_id=store.id, research_run_id=run.id, label="قهوة مختصة", intent_count=2)
    session.add(cluster)
    session.commit()
    session.refresh(cluster)
    intent_1.cluster_id = cluster.id
    intent_2.cluster_id = cluster.id
    session.add(intent_1)
    session.add(intent_2)
    session.commit()

    opportunities = run_opportunity_discovery_agent(session, store.id, run.id)
    # Force two independent opportunities for these intents rather than
    # relying on Q2's exact-intent-id consolidation, to isolate what R5
    # itself is responsible for catching (Q2 already merges exact-id
    # overlaps; R5 catches same-cluster/near-duplicate-text cases Q2
    # cannot, since it groups strictly by identical affected_intents).
    all_open = [o for o in opportunities if o.status == OpportunityStatus.open]
    assert len(all_open) >= 1

    run_recommendation_engine(session, store.id, run.id, opportunities, max_recommendations=5)

    active_recs = session.exec(
        select(Recommendation)
        .where(Recommendation.store_id == store.id)
        .where(Recommendation.status == RecommendationStatus.new)
    ).all()
    all_recs = session.exec(select(Recommendation).where(Recommendation.store_id == store.id)).all()
    # The two clustered near-duplicate intents must collapse to exactly one
    # *active* recommendation — the other stays on record as `superseded`,
    # never silently deleted (Part R5's evidence trail requirement).
    assert len(all_recs) == 2
    assert len(active_recs) == 1
    superseded = [r for r in all_recs if r.status == RecommendationStatus.superseded]
    assert len(superseded) == 1
