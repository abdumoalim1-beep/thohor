"""Regression test for a real bug caught during live verification:
_resolve_competitor_names/_resolve_competitor_domain_names only filtered
out user_rejected competitors, so every other classification value —
including 'social' and 'video' — was treated as a real competitor. A live
run showed Instagram and YouTube listed among a store's 'top 5
competitors'. Fixed by reusing is_business_competitor (classification ==
'direct_competitor'), the one predicate this codebase already uses
everywhere else to decide 'show this as a competitor'."""

from app.ai_visibility.visibility_orchestration import _resolve_competitor_domain_names, _resolve_competitor_names
from app.models.competitor import Competitor, CompetitorType
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store


def _make_store(session):
    org = Organization(name="t", slug="t-competitor-filter")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://flowery.example")
    session.add(store)
    session.commit()
    session.refresh(store)
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)
    return store, run


def _competitor(store_id, run_id, *, domain, name, classification, confirmation_status="auto_confirmed"):
    return Competitor(
        store_id=store_id, domain=domain, name=name, competitor_type=CompetitorType.identity_web_search,
        first_seen_research_run_id=run_id, classification=classification, confirmation_status=confirmation_status,
    )


def test_social_and_video_platforms_are_excluded_from_competitor_names(session):
    store, run = _make_store(session)
    session.add_all([
        _competitor(store.id, run.id, domain="instagram.com", name="Instagram", classification="social"),
        _competitor(store.id, run.id, domain="youtube.com", name="Youtube", classification="video"),
        _competitor(store.id, run.id, domain="real-competitor.com", name="منافس حقيقي", classification="direct_competitor"),
    ])
    session.commit()

    names = _resolve_competitor_names(session, store.id)

    assert names == ["منافس حقيقي"]


def test_unknown_classification_is_also_excluded(session):
    """A SERP-mined competitor that never earned a real classification
    (still 'unknown') isn't a confirmed business competitor either —
    is_business_competitor requires 'direct_competitor' specifically."""
    store, run = _make_store(session)
    session.add(_competitor(store.id, run.id, domain="maybe.com", name="ربما منافس", classification="unknown"))
    session.commit()

    assert _resolve_competitor_names(session, store.id) == []
    assert _resolve_competitor_domain_names(session, store.id) == {}


def test_domain_names_dict_only_has_real_competitors(session):
    store, run = _make_store(session)
    session.add_all([
        _competitor(store.id, run.id, domain="instagram.com", name="Instagram", classification="social"),
        _competitor(store.id, run.id, domain="real-competitor.com", name="منافس حقيقي", classification="direct_competitor"),
    ])
    session.commit()

    domain_names = _resolve_competitor_domain_names(session, store.id)

    assert domain_names == {"real-competitor.com": "منافس حقيقي"}
    assert "instagram.com" not in domain_names


def test_user_rejected_stays_excluded_even_if_classified_direct_competitor(session):
    """A human explicitly said 'not a competitor' — that verdict must
    still win even over a real classification, same as everywhere else
    this field is read."""
    store, run = _make_store(session)
    session.add(_competitor(
        store.id, run.id, domain="rejected.com", name="مرفوض", classification="direct_competitor",
        confirmation_status="user_rejected",
    ))
    session.commit()

    assert _resolve_competitor_names(session, store.id) == []
