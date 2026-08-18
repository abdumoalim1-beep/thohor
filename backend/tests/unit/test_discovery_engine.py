from sqlmodel import select

from app.competitors.discovery_engine import (
    _derive_display_name,
    mine_ai_visibility_competitors,
    mine_serp_competitors,
    run_competitor_discovery_agent,
)
from app.intent.intent_engine import _attach_keywords
from app.models.ai_visibility import AIVisibilityObservation, PromptFamily, PromptVariant
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.intent import Intent, IntentSource, Keyword
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store


def _make_store_with_intent(session):
    org = Organization(name="t", slug="t-discovery")
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
    intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="topic",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(intent)
    session.commit()
    session.refresh(intent)
    _attach_keywords(session, intent, ["keyword"], "sa", "ar")
    return store, run, intent


def test_discovery_mines_serp_and_ai_visibility_excluding_own_domain(session):
    store, run, intent = _make_store_with_intent(session)

    keyword = session.exec(select(Keyword)).one()
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[
                {"rank": 1, "domain": "www.rival-one.co", "url": "https://www.rival-one.co/x"},
                {"rank": 2, "domain": "store.example", "url": "https://store.example/product"},
                {"rank": 3, "domain": "rival-two.co", "url": "https://rival-two.co/y"},
            ],
            client_rank=2,
            client_url="https://store.example/product",
        )
    )
    session.commit()

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="question")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    session.add(
        AIVisibilityObservation(
            store_id=store.id,
            intent_id=intent.id,
            prompt_variant_id=variant.id,
            research_run_id=run.id,
            provider="openai",
            model="gpt-4o-mini",
            country="sa",
            language="ar",
            mentioned=False,
            citations=["https://rival-two.co/y", "https://store.example/about", "https://rival-three.co/z"],
        )
    )
    session.commit()

    relationships = run_competitor_discovery_agent(
        session=session,
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
    )

    # rival-one, rival-two (serp) + rival-two, rival-three (ai) = 4 relationships,
    # store.example excluded from both sources
    assert len(relationships) == 4

    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    domains = {c.domain for c in competitors}
    assert domains == {"rival-one.co", "rival-two.co", "rival-three.co"}
    assert "store.example" not in domains

    rival_one = next(c for c in competitors if c.domain == "rival-one.co")
    assert rival_one.competitor_type == CompetitorType.search_competitor

    rival_three = next(c for c in competitors if c.domain == "rival-three.co")
    assert rival_three.competitor_type == CompetitorType.ai_recommendation_competitor

    # rival-two appears in both surfaces; first-seen type (serp) wins
    rival_two = next(c for c in competitors if c.domain == "rival-two.co")
    assert rival_two.competitor_type == CompetitorType.search_competitor
    rival_two_relationships = [r for r in relationships if r.competitor_id == rival_two.id]
    assert {r.source for r in rival_two_relationships} == {RelationshipSource.serp, RelationshipSource.ai_visibility}


def test_mine_serp_competitors_never_persists_synthetic_test_domains(session):
    """Part R7 — traced root cause: MockSearchProvider's deterministic
    'example-competitor-N.test' domains (or a ReplaySearchProvider replaying
    old mock-sourced serp_observations) must never become real Competitor
    rows, regardless of which upstream code path produced them."""
    store, run, intent = _make_store_with_intent(session)
    keyword = session.exec(select(Keyword)).one()
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[
                {"rank": 1, "domain": "example-competitor-1.test", "url": "https://example-competitor-1.test/x"},
                {"rank": 2, "domain": "example-competitor-2.test", "url": "https://example-competitor-2.test/y"},
                {"rank": 3, "domain": "real-rival.sa", "url": "https://real-rival.sa/z"},
            ],
            client_rank=None,
        )
    )
    session.commit()

    relationships = mine_serp_competitors(session, store.id, store.url, run.id)

    assert len(relationships) == 1
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert {c.domain for c in competitors} == {"real-rival.sa"}


def test_mine_ai_visibility_competitors_never_persists_synthetic_test_domains(session):
    store, run, intent = _make_store_with_intent(session)
    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="question")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    session.add(
        AIVisibilityObservation(
            store_id=store.id,
            intent_id=intent.id,
            prompt_variant_id=variant.id,
            research_run_id=run.id,
            provider="openai",
            model="gpt-4o-mini",
            country="sa",
            language="ar",
            mentioned=False,
            citations=["https://example-competitor-3.test/x"],
            competitors_mentioned=["example-competitor-4.test", "real-rival.sa"],
        )
    )
    session.commit()

    relationships = mine_ai_visibility_competitors(session, store.id, store.url, run.id)

    assert len(relationships) == 1
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert {c.domain for c in competitors} == {"real-rival.sa"}


def test_discovery_returns_empty_when_no_data(session):
    store, run, intent = _make_store_with_intent(session)

    relationships = run_competitor_discovery_agent(
        session=session,
        store_id=store.id,
        store_url=store.url,
        research_run_id=run.id,
        agent_run_id=None,
    )

    assert relationships == []


def test_mine_ai_visibility_competitors_mines_text_mentions_not_just_citation_urls(session):
    """Part G-B5 regression: a real, non-grounded chat completion almost
    never contains a raw citation URL (no AI surface has search grounding
    enabled — Part C #4), so AIVisibilityObservation.citations is usually
    empty. The actual signal is competitors_mentioned (brand/domain names
    matched deterministically in the response text) — this was being
    collected and persisted but never mined into a CompetitorRelationship
    before this fix, which is why detect_ai_citation_gap_opportunities
    (app.opportunities.detectors) almost never had a competitor to compare
    against."""
    store, run, intent = _make_store_with_intent(session)

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="question")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    session.add(
        AIVisibilityObservation(
            store_id=store.id,
            intent_id=intent.id,
            prompt_variant_id=variant.id,
            research_run_id=run.id,
            provider="openai",
            model="gpt-4o-mini",
            country="sa",
            language="ar",
            mentioned=False,
            citations=[],  # no grounding -> no URLs, the realistic case
            competitors_mentioned=["rival.co"],
        )
    )
    session.commit()

    relationships = mine_ai_visibility_competitors(session, store.id, store.url, run.id)

    assert len(relationships) == 1
    assert relationships[0].source == RelationshipSource.ai_visibility
    competitor = session.get(Competitor, relationships[0].competitor_id)
    assert competitor.domain == "rival.co"
    assert competitor.competitor_type == CompetitorType.ai_recommendation_competitor


def test_mine_ai_visibility_competitors_deduplicates_domain_from_citation_and_mention(session):
    """The same domain appearing in both citations (URL) and
    competitors_mentioned (text match) for one observation must produce
    exactly one relationship, not two."""
    store, run, intent = _make_store_with_intent(session)

    family = PromptFamily(intent_id=intent.id, research_run_id=run.id)
    session.add(family)
    session.commit()
    session.refresh(family)
    variant = PromptVariant(prompt_family_id=family.id, text="question")
    session.add(variant)
    session.commit()
    session.refresh(variant)

    session.add(
        AIVisibilityObservation(
            store_id=store.id,
            intent_id=intent.id,
            prompt_variant_id=variant.id,
            research_run_id=run.id,
            provider="openai",
            model="gpt-4o-mini",
            country="sa",
            language="ar",
            mentioned=False,
            citations=["https://rival.co/best-grinders"],
            competitors_mentioned=["rival.co"],
        )
    )
    session.commit()

    relationships = mine_ai_visibility_competitors(session, store.id, store.url, run.id)
    assert len(relationships) == 1


def test_mine_serp_competitors_is_the_serp_only_half(session):
    store, run, intent = _make_store_with_intent(session)
    keyword = session.exec(select(Keyword)).one()
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "rival-one.co", "url": "https://rival-one.co/x"}],
            client_rank=None,
        )
    )
    session.commit()

    relationships = mine_serp_competitors(session, store.id, store.url, run.id)

    assert len(relationships) == 1
    assert relationships[0].source == RelationshipSource.serp
    competitors = session.exec(select(Competitor).where(Competitor.store_id == store.id)).all()
    assert len(competitors) == 1
    assert competitors[0].domain == "rival-one.co"


def test_derive_display_name_produces_a_readable_brand_name_not_a_bare_domain():
    """Part G-B6 finding: Competitor.name used to equal Competitor.domain
    verbatim, so detect_competitors_mentioned (visibility_engine.py) was
    matching a bare hostname string against natural AI response text —
    which essentially never contains 'amazon.sa' literally, even when the
    response clearly discusses Amazon."""
    assert _derive_display_name("amazon.sa") == "Amazon"
    assert _derive_display_name("www.rival-coffee.example") == "Rival Coffee"
    assert _derive_display_name("noon.com") == "Noon"


def test_get_or_create_competitor_sets_readable_name(session):
    store, run, intent = _make_store_with_intent(session)
    keyword = session.exec(select(Keyword)).one()
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=intent.id,
            keyword_id=keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "some-rival.co", "url": "https://some-rival.co/x"}],
            client_rank=None,
        )
    )
    session.commit()

    mine_serp_competitors(session, store.id, store.url, run.id)

    competitor = session.exec(select(Competitor).where(Competitor.store_id == store.id)).one()
    assert competitor.name == "Some Rival"
    assert competitor.domain == "some-rival.co"
