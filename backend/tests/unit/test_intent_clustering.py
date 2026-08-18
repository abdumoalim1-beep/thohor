"""Part Q1 — deterministic intent clustering (beyond G-B1's near-duplicate
rejection). No AI call, so these are ordinary state-based unit tests."""

from sqlmodel import select

from app.intent.clustering import cluster_intents
from app.models.intent import Intent, IntentSource
from app.models.intent_cluster import IntentCluster
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-intent-clustering")
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


def _make_intent(session, store, run, topic, *, category=None, quality_score=1.0, is_accepted=True):
    intent = Intent(
        store_id=store.id, research_run_id=run.id, topic=topic, category=category, country="sa", language="ar",
        source=IntentSource.ai_expansion, quality_score=quality_score, is_accepted=is_accepted,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    return intent


def test_related_intents_in_the_same_category_join_one_cluster(session):
    store, run = _make_store_and_run(session)
    # Note: content tokens are compared as literal words (no stemming/
    # definite-article stripping — same simple approach as
    # app.intent.quality), so these examples deliberately avoid the "ال"
    # prefix ambiguity between e.g. "قهوة" and "القهوة" to keep the
    # expected overlap unambiguous.
    a = _make_intent(session, store, run, "قهوة مختصة", category="القهوة", quality_score=0.9)
    b = _make_intent(session, store, run, "معدات تحضير قهوة مختصة", category="القهوة", quality_score=0.7)
    c = _make_intent(session, store, run, "طريقة عمل قهوة مختصة في المنزل", category="القهوة", quality_score=0.6)

    clusters = cluster_intents(session, store.id, run.id, [a, b, c])

    assert len(clusters) == 1
    assert clusters[0].intent_count == 3
    assert clusters[0].label == "قهوة مختصة"  # highest quality_score member
    session.refresh(a)
    session.refresh(b)
    session.refresh(c)
    assert a.cluster_id == b.cluster_id == c.cluster_id == clusters[0].id


def test_unrelated_intents_get_separate_clusters(session):
    store, run = _make_store_and_run(session)
    coffee = _make_intent(session, store, run, "قهوة مختصة", category="القهوة")
    shoes = _make_intent(session, store, run, "أحذية رياضية رجالية", category="الأحذية")

    clusters = cluster_intents(session, store.id, run.id, [coffee, shoes])

    assert len(clusters) == 2
    session.refresh(coffee)
    session.refresh(shoes)
    assert coffee.cluster_id != shoes.cluster_id


def test_same_category_but_unrelated_topics_still_split_into_separate_clusters(session):
    """Sharing a category alone isn't enough — content-token overlap
    within the category still gates whether two intents are the same
    cluster or two different ones."""
    store, run = _make_store_and_run(session)
    grinders = _make_intent(session, store, run, "مطحنة قهوة يدوية", category="القهوة")
    beans = _make_intent(session, store, run, "حبوب البن الإثيوبي الفاخر", category="القهوة")

    clusters = cluster_intents(session, store.id, run.id, [grinders, beans])

    assert len(clusters) == 2


def test_rejected_intents_are_never_clustered(session):
    store, run = _make_store_and_run(session)
    accepted = _make_intent(session, store, run, "قهوة مختصة", category="القهوة", is_accepted=True)
    rejected = _make_intent(session, store, run, "سياسة الخصوصية", is_accepted=False)

    clusters = cluster_intents(session, store.id, run.id, [accepted, rejected])

    assert len(clusters) == 1
    session.refresh(accepted)
    session.refresh(rejected)
    assert accepted.cluster_id is not None
    assert rejected.cluster_id is None


def test_a_standalone_intent_still_gets_its_own_cluster_of_one(session):
    store, run = _make_store_and_run(session)
    lonely = _make_intent(session, store, run, "قهوة مختصة", category="القهوة")

    clusters = cluster_intents(session, store.id, run.id, [lonely])

    assert len(clusters) == 1
    assert clusters[0].intent_count == 1
    assert clusters[0].label == "قهوة مختصة"


def test_intents_with_no_category_still_cluster_by_token_overlap(session):
    store, run = _make_store_and_run(session)
    a = _make_intent(session, store, run, "قهوة مختصة", category=None)
    b = _make_intent(session, store, run, "افضل قهوة مختصة بالرياض", category=None)

    clusters = cluster_intents(session, store.id, run.id, [a, b])

    assert len(clusters) == 1
    assert clusters[0].category is None


def test_no_accepted_intents_produces_no_clusters(session):
    store, run = _make_store_and_run(session)
    rejected = _make_intent(session, store, run, "سياسة الخصوصية", is_accepted=False)

    clusters = cluster_intents(session, store.id, run.id, [rejected])

    assert clusters == []
    assert session.exec(select(IntentCluster)).all() == []
