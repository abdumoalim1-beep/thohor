"""Part R1 (Round 1 remediation) — canonical-entity refresh vs immutable
observation. Confirmed root cause of extra.com's 0/30 accepted intents in
Round 1: _get_or_create_category (now _upsert_category) never refreshed
Category.name on a repeat crawl of the same URL, so a Category row created
by a buggy extractor (scraped <title> instead of <h1>) stayed wrong
forever. These tests prove the fix and the canonical-vs-observation split
it depends on, entirely offline (SQLite fixture, no network/API calls)."""

import uuid

from sqlmodel import select

from app.crawler.store_intelligence import _ensure_fallback_brand, _upsert_brand, _upsert_category
from app.intent.intent_engine import generate_deterministic_seed_intents
from app.intent.quality import apply_quality_gate
from app.models.catalog import Category
from app.models.observation import PageObservation
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store

SCRAPED_TITLE_GARBAGE = "Academic | \n     Books to Scrape - Sandbox"
CORRECT_H1 = "Academic"


def _make_store(session, url="https://example-remediation.test"):
    org = Organization(name="t", slug=f"t-r1-{uuid.uuid4().hex[:8]}")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url=url)
    session.add(store)
    session.commit()
    session.refresh(store)
    return store


def test_upsert_category_creates_new_row_for_a_new_url(session):
    store = _make_store(session)

    category = _upsert_category(session, store.id, "Coffee Tools", "https://store.test/c/coffee-tools")

    rows = session.exec(select(Category).where(Category.store_id == store.id)).all()
    assert len(rows) == 1
    assert rows[0].id == category.id
    assert rows[0].name == "Coffee Tools"


def test_upsert_category_refreshes_a_stale_name_on_repeat_crawl(session):
    """The exact extra.com scenario: an old crawl (buggy extractor) wrote
    a scraped-title-shaped name; a later crawl with the fixed extractor
    must overwrite it in place, not leave the stale row untouched."""
    store = _make_store(session)
    url = "https://store.test/c/academic"

    stale = _upsert_category(session, store.id, SCRAPED_TITLE_GARBAGE, url)
    stale_id = stale.id

    refreshed = _upsert_category(session, store.id, CORRECT_H1, url)

    assert refreshed.id == stale_id  # same canonical row, not a duplicate
    assert refreshed.name == CORRECT_H1

    rows = session.exec(select(Category).where(Category.store_id == store.id).where(Category.url == url)).all()
    assert len(rows) == 1
    assert rows[0].name == CORRECT_H1


def test_upsert_category_refresh_never_touches_historical_page_observations(session):
    """Canonical entity (Category) is mutable; historical observations
    (PageObservation, one immutable row per crawl) are not. Refreshing the
    canonical name must never rewrite a prior run's observation."""
    store = _make_store(session)
    url = "https://store.test/c/academic"

    _upsert_category(session, store.id, SCRAPED_TITLE_GARBAGE, url)

    old_run = ResearchRun(store_id=store.id)
    session.add(old_run)
    session.commit()
    session.refresh(old_run)

    old_observation = PageObservation(
        store_id=store.id,
        research_run_id=old_run.id,
        page_id=uuid.uuid4(),
        source_url=url,
        source="crawler",
        extractor_version="v-old-buggy",
        normalized_extraction={"title": SCRAPED_TITLE_GARBAGE, "h1": None},
        extracted_entities={},
    )
    session.add(old_observation)
    session.commit()
    session.refresh(old_observation)

    _upsert_category(session, store.id, CORRECT_H1, url)

    session.refresh(old_observation)
    assert old_observation.normalized_extraction["title"] == SCRAPED_TITLE_GARBAGE
    assert old_observation.extractor_version == "v-old-buggy"


def test_upsert_category_is_a_noop_when_name_is_unchanged(session):
    store = _make_store(session)
    url = "https://store.test/c/x"
    first = _upsert_category(session, store.id, "Coffee Tools", url)

    second = _upsert_category(session, store.id, "Coffee Tools", url)

    assert second.id == first.id
    rows = session.exec(select(Category).where(Category.store_id == store.id)).all()
    assert len(rows) == 1  # no duplicate row created


def test_upsert_brand_promotes_domain_guessed_name_when_real_brand_arrives(session):
    """Part R1 — the same staleness bug applies to Brand.name, not just
    Category.name: _ensure_fallback_brand's domain-derived guess must be
    promotable, not stuck forever once a real JSON-LD brand name is found
    on a later crawl."""
    store = _make_store(session, url="https://roastinghouse.sa")

    _ensure_fallback_brand(session, store.id, store.url)
    from app.models.catalog import Brand

    guessed = session.exec(select(Brand).where(Brand.store_id == store.id)).one()
    assert guessed.name == "Roastinghouse"

    promoted = _upsert_brand(session, store.id, "Roasting House Co.", store.url)

    assert promoted.id == guessed.id
    assert promoted.name == "Roasting House Co."
    assert "Roastinghouse" in promoted.aliases  # old guess preserved for mention-matching


def test_upsert_brand_never_flip_flops_between_two_real_names(session):
    """A genuinely real (non-guessed) existing name must never be silently
    replaced by a different real name — accumulate as an alias instead, so
    a multi-brand store doesn't flip-flop its canonical name arbitrarily."""
    store = _make_store(session, url="https://roastinghouse.sa")

    first = _upsert_brand(session, store.id, "Roasting House Co.", store.url)
    second = _upsert_brand(session, store.id, "A Different Real Brand", store.url)

    assert second.id == first.id
    assert second.name == "Roasting House Co."  # unchanged
    assert "A Different Real Brand" in second.aliases


async def test_extra_com_shaped_scenario_stale_category_blocks_intents_until_refreshed(session):
    """End-to-end regression for the confirmed Round 1 failure: a store
    whose Category rows are all scraped-title garbage produces 0 accepted
    intents; after a re-crawl refreshes them via _upsert_category (the
    fix), deterministic seed intents are generated and pass the quality
    gate. No network/API calls anywhere in this test."""
    store = _make_store(session, url="https://extra-shaped.test")
    run = ResearchRun(store_id=store.id)
    session.add(run)
    session.commit()
    session.refresh(run)

    garbage_categories = [
        _upsert_category(session, store.id, f"{name} | \n     Extra-Shaped Store", f"https://extra-shaped.test/c/{i}")
        for i, name in enumerate(["Air Fryers", "Guitars", "Home Essentials"])
    ]

    intents_before = generate_deterministic_seed_intents(
        session, store_id=store.id, research_run_id=run.id, categories=garbage_categories,
        country="sa", language="ar", max_intents=10,
    )
    accepted_before = apply_quality_gate(session, intents_before, store.id)
    assert accepted_before == []  # exactly extra.com's confirmed 0-accepted-intents failure

    refreshed_categories = [
        _upsert_category(session, store.id, name, f"https://extra-shaped.test/c/{i}")
        for i, name in enumerate(["Air Fryers", "Guitars", "Home Essentials"])
    ]
    assert [c.id for c in refreshed_categories] == [c.id for c in garbage_categories]  # same canonical rows

    run_2 = ResearchRun(store_id=store.id)
    session.add(run_2)
    session.commit()
    session.refresh(run_2)

    intents_after = generate_deterministic_seed_intents(
        session, store_id=store.id, research_run_id=run_2.id, categories=refreshed_categories,
        country="sa", language="ar", max_intents=10,
    )
    accepted_after = apply_quality_gate(session, intents_after, store.id)

    assert len(accepted_after) == 3
    assert {i.topic for i in accepted_after} == {"Air Fryers", "Guitars", "Home Essentials"}
