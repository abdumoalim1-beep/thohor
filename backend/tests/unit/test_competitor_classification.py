import uuid

from sqlmodel import select

from app.competitors.classification import (
    assess_vertical_relevance,
    classify_competitors_for_run,
    classify_known_domain,
    is_business_competitor,
)
from app.models.catalog import Category
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.stable_intent import StableIntent
from app.models.store import Store


def _make_store_and_run(session):
    org = Organization(name="t", slug="t-competitor-classification")
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


def _make_stable_intent(session, store, topic):
    stable_intent = StableIntent(
        store_id=store.id, canonical_topic=topic, normalized_topic=topic.lower(), country="sa", language="ar",
        locale="sa_ar",
    )
    session.add(stable_intent)
    session.commit()
    session.refresh(stable_intent)
    return stable_intent


def _make_competitor(session, store, run, domain):
    competitor = Competitor(
        store_id=store.id, domain=domain, name=domain, competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    return competitor


def test_classify_known_domain_detects_marketplace_social_video_government():
    assert classify_known_domain("amazon.sa")[0] == "marketplace"
    assert classify_known_domain("www.noon.com")[0] == "marketplace"
    assert classify_known_domain("facebook.com")[0] == "social"
    assert classify_known_domain("youtube.com")[0] == "video"
    assert classify_known_domain("moh.gov.sa")[0] == "government"
    assert classify_known_domain("apps.apple.com")[0] == "irrelevant"


def test_classify_known_domain_returns_none_for_unrecognized_domain():
    assert classify_known_domain("some-coffee-shop.sa") is None


# Part R3.4 (Round 1 remediation) — explicit regression suite. The
# confirmed Round 1 bug: ar.wikipedia.org was classified direct_competitor
# because the old check only ever stripped a literal "www." prefix before
# an exact-string lookup against a curated set containing bare
# "wikipedia.org" — any other subdomain silently fell through to the
# generic (wrong) fallback classifier.
class TestWikipediaRegression:
    def test_bare_wikipedia_is_publisher(self):
        assert classify_known_domain("wikipedia.org")[0] == "publisher"

    def test_www_wikipedia_is_publisher(self):
        assert classify_known_domain("www.wikipedia.org")[0] == "publisher"

    def test_arabic_subdomain_wikipedia_is_publisher(self):
        assert classify_known_domain("ar.wikipedia.org")[0] == "publisher"

    def test_english_subdomain_wikipedia_is_publisher(self):
        assert classify_known_domain("en.wikipedia.org")[0] == "publisher"

    def test_wikipedia_can_never_become_direct_competitor(self, session):
        """End-to-end through the real classifier, not just the curated
        lookup — proves the whole pipeline, including the catalog-overlap
        fallback, can never override a curated 'publisher' verdict."""
        store, run = _make_store_and_run(session)
        session.add(Category(store_id=store.id, name="قهوة"))
        session.commit()
        stable_intent_a = _make_stable_intent(session, store, "قهوة")
        stable_intent_b = _make_stable_intent(session, store, "تاريخ القهوة")
        wiki = _make_competitor(session, store, run, "ar.wikipedia.org")
        for stable_intent in (stable_intent_a, stable_intent_b):
            session.add(
                CompetitorRelationship(
                    competitor_id=wiki.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
                )
            )
        session.commit()

        classify_competitors_for_run(session, store.id, run.id)

        session.refresh(wiki)
        assert wiki.classification == "publisher"
        assert is_business_competitor(wiki) is False


class TestOtherKnownCategoryRegressions:
    def test_government_subdomain(self):
        assert classify_known_domain("moh.gov.sa")[0] == "government"

    def test_bare_gov(self):
        assert classify_known_domain("irs.gov")[0] == "government"

    def test_educational_domain(self):
        assert classify_known_domain("ksu.edu.sa")[0] == "educational"
        assert classify_known_domain("mit.edu")[0] == "educational"

    def test_social_domains_and_subdomains(self):
        assert classify_known_domain("facebook.com")[0] == "social"
        assert classify_known_domain("m.facebook.com")[0] == "social"
        assert classify_known_domain("x.com")[0] == "social"

    def test_forum_domains(self):
        assert classify_known_domain("reddit.com")[0] == "forum"
        assert classify_known_domain("quora.com")[0] == "forum"

    def test_common_marketplaces(self):
        assert classify_known_domain("amazon.sa")[0] == "marketplace"
        assert classify_known_domain("noon.com")[0] == "marketplace"
        assert classify_known_domain("aliexpress.com")[0] == "marketplace"

    def test_wholesale_b2b_platforms(self):
        """Part R3 — Round 1 confirmed both of these misclassified as
        direct retail competitors for allbirds.com."""
        assert classify_known_domain("alibaba.com")[0] == "wholesale"
        assert classify_known_domain("arabic.alibaba.com")[0] == "wholesale"
        assert classify_known_domain("made-in-china.com")[0] == "wholesale"
        assert classify_known_domain("sa.made-in-china.com")[0] == "wholesale"

    def test_health_info_sites_confirmed_in_round_1(self):
        assert classify_known_domain("webteb.com")[0] == "publisher"
        assert classify_known_domain("altibbi.com")[0] == "publisher"

    def test_app_store_domains_are_hostname_specific_not_registered_domain(self):
        """apps.apple.com must match, but apple.com itself (a real
        possible competitor site, e.g. if a store sold Apple accessories)
        must not be swept in just because it shares a registered domain
        with the app store subdomain."""
        assert classify_known_domain("apps.apple.com")[0] == "irrelevant"
        assert classify_known_domain("play.google.com")[0] == "irrelevant"
        assert classify_known_domain("apple.com") is None

    def test_google_itself_is_never_a_competitor(self):
        """Part R3 — Round 1 confirmed google.com classified as a direct
        competitor for roastinghouse.sa (a SERP-own feature surfacing as a
        result domain, not a real business)."""
        assert classify_known_domain("google.com")[0] == "irrelevant"
        assert classify_known_domain("www.google.com")[0] == "irrelevant"


def test_classify_competitors_for_run_labels_known_noise_domains_correctly(session):
    store, run = _make_store_and_run(session)
    stable_intent = _make_stable_intent(session, store, "قهوة مختصة")

    youtube = _make_competitor(session, store, run, "youtube.com")
    session.add(
        CompetitorRelationship(
            competitor_id=youtube.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
            research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
        )
    )
    session.commit()

    classify_competitors_for_run(session, store.id, run.id)

    session.refresh(youtube)
    assert youtube.classification == "video"
    assert youtube.relevance_score == 0.0
    assert is_business_competitor(youtube) is False


def test_classify_competitors_for_run_labels_repeated_catalog_overlapping_domain_as_direct(session):
    store, run = _make_store_and_run(session)
    session.add(Category(store_id=store.id, name="قهوة مختصة"))
    session.commit()

    intent_a = _make_stable_intent(session, store, "قهوة مختصة")
    intent_b = _make_stable_intent(session, store, "حبوب قهوة")
    rival = _make_competitor(session, store, run, "rival-coffee.example")

    for stable_intent, title in [(intent_a, "أفضل قهوة مختصة في السعودية"), (intent_b, "حبوب قهوة محمصة طازجة")]:
        session.add(
            SerpObservation(
                store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                keyword_id=uuid.uuid4(), research_run_id=run.id, country="sa", language="ar",
                results=[{"rank": 1, "domain": "rival-coffee.example", "url": "https://rival-coffee.example/x", "title": title}],
            )
        )
        session.add(
            CompetitorRelationship(
                competitor_id=rival.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()

    classify_competitors_for_run(session, store.id, run.id)

    session.refresh(rival)
    assert rival.classification == "direct_competitor"
    assert rival.relevance_score > 0
    assert len(rival.shared_stable_intents) == 2
    assert is_business_competitor(rival) is True


def test_classify_competitors_for_run_uses_intent_topics_when_catalog_is_empty(session):
    """Part G-B6 regression: several real stores in the live benchmark have
    zero Category/Product rows (a crawler-extraction gap) or a
    catalog/SERP-title language mismatch, so catalog_tokens alone was never
    non-empty enough to classify any competitor as direct_competitor.
    Intent.topic (always present, generated in the store's target_language)
    must be able to carry the overlap signal on its own, with zero
    categories/products in the DB."""
    store, run = _make_store_and_run(session)
    # Deliberately no Category/Product rows for this store — Intent.topic
    # is all there is, across both intents (Part R2-F3's stricter
    # topic-only bar of 3 shared words needs the full intent set, not just
    # one, to clear — matching what a real run would actually persist).
    for topic in ("قهوة مختصة", "حبوب قهوة"):
        session.add(
            Intent(
                store_id=store.id, research_run_id=run.id, topic=topic,
                country="sa", language="ar", source=IntentSource.ai_expansion,
            )
        )
    session.commit()

    intent_a = _make_stable_intent(session, store, "قهوة مختصة")
    intent_b = _make_stable_intent(session, store, "حبوب قهوة")
    rival = _make_competitor(session, store, run, "rival-coffee.example")

    for stable_intent, title in [(intent_a, "أفضل قهوة مختصة في السعودية"), (intent_b, "حبوب قهوة محمصة طازجة")]:
        session.add(
            SerpObservation(
                store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                keyword_id=uuid.uuid4(), research_run_id=run.id, country="sa", language="ar",
                results=[{"rank": 1, "domain": "rival-coffee.example", "url": "https://rival-coffee.example/x", "title": title}],
            )
        )
        session.add(
            CompetitorRelationship(
                competitor_id=rival.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()

    classify_competitors_for_run(session, store.id, run.id)

    session.refresh(rival)
    assert rival.classification == "direct_competitor"


def test_classify_competitors_for_run_single_intent_stays_unknown(session):
    store, run = _make_store_and_run(session)
    stable_intent = _make_stable_intent(session, store, "قهوة مختصة")
    obscure = _make_competitor(session, store, run, "obscure-site.example")
    session.add(
        CompetitorRelationship(
            competitor_id=obscure.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
            research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=5,
        )
    )
    session.commit()

    classify_competitors_for_run(session, store.id, run.id)

    session.refresh(obscure)
    assert obscure.classification == "unknown"
    assert is_business_competitor(obscure) is False


def test_classify_competitors_for_run_populates_evidence_ids(session):
    store, run = _make_store_and_run(session)
    session.add(Category(store_id=store.id, name="قهوة"))
    session.commit()

    intent_a = _make_stable_intent(session, store, "قهوة مختصة")
    intent_b = _make_stable_intent(session, store, "قهوة عربية")
    rival = _make_competitor(session, store, run, "rival-coffee.example")

    for stable_intent in (intent_a, intent_b):
        observation = SerpObservation(
            store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id, keyword_id=uuid.uuid4(),
            research_run_id=run.id, country="sa", language="ar",
            results=[{"rank": 1, "domain": "rival-coffee.example", "url": "https://rival-coffee.example/x", "title": "قهوة"}],
        )
        session.add(observation)
        session.commit()
        session.refresh(observation)
        session.add(
            Evidence(
                store_id=store.id, research_run_id=run.id, source_type=EvidenceSourceType.serp_observation,
                source_id=observation.id, confidence=1.0, summary="e",
            )
        )
        session.add(
            CompetitorRelationship(
                competitor_id=rival.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
            )
        )
    session.commit()

    classify_competitors_for_run(session, store.id, run.id)

    session.refresh(rival)
    assert len(rival.evidence_ids) == 2


# --- Part R2-F3: Vertical Relevance Gate — pure function unit tests ------


def test_assess_vertical_relevance_rejects_generic_word_only_overlap():
    """The exact confirmed Round 2 bug: a domain whose SERP titles only
    share generic marketing words ('آمن'/'safe') with the store's own
    catalog tokens must never be treated as commercial-intersection
    evidence."""
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"حلول", "آمن", "للحماية"},
        real_catalog_tokens={"تسوق", "آمن"},
        shared_intent_count=2,
    )
    assert result.is_eligible_for_direct is False


def test_assess_vertical_relevance_accepts_specific_multi_word_overlap():
    result = assess_vertical_relevance(
        domain_tokens={"القهوة"}, title_tokens={"مطحنة", "قهوة", "مختصة", "للبيع"},
        real_catalog_tokens={"قهوة", "مختصة", "مطحنة"},
        shared_intent_count=3,
    )
    assert result.is_eligible_for_direct is True
    assert result.relevance_score >= 0.5
    assert result.classification_confidence > 0.5


def test_assess_vertical_relevance_rejects_single_specific_word_overlap():
    """One specific shared word alone (below MIN_MEANINGFUL_OVERLAP_TOKENS)
    still isn't enough — genuinely distinct businesses can coincidentally
    share exactly one real word."""
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"قهوة", "قطارات", "رحلات"},
        real_catalog_tokens={"قهوة", "أكواب", "مطحنة"},
        shared_intent_count=2,
    )
    assert result.is_eligible_for_direct is False


def test_assess_vertical_relevance_requires_minimum_shared_intents_even_with_specific_overlap():
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"قهوة", "مختصة"},
        real_catalog_tokens={"قهوة", "مختصة"},
        shared_intent_count=1,
    )
    assert result.is_eligible_for_direct is False


def test_assess_vertical_relevance_topic_only_overlap_needs_more_words_than_real_catalog():
    """Part R2-F3 — the confirmed ef.com bug: when no real catalog exists,
    a SERP result merely echoing the search query's own words back must
    NOT be enough at the same low bar a real catalog match would clear;
    it needs 3+ shared words (MIN_MEANINGFUL_OVERLAP_TOKENS_TOPIC_ONLY),
    not 2."""
    # Exactly 2 shared topic words, no real catalog at all -> still rejected.
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"منتجات", "صديقة", "للسفر"},
        real_catalog_tokens=set(), intent_topic_tokens={"منتجات", "صديقة", "للبيئة"},
        shared_intent_count=2,
    )
    assert result.is_eligible_for_direct is False

    # 3 shared topic words clears the higher topic-only bar.
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"منتجات", "صديقة", "للبيئة", "رخيصة"},
        real_catalog_tokens=set(), intent_topic_tokens={"منتجات", "صديقة", "للبيئة"},
        shared_intent_count=2,
    )
    assert result.is_eligible_for_direct is True


def test_assess_vertical_relevance_real_catalog_overlap_ignores_topic_echo():
    """When a real catalog exists, topic-word echo alone (no real-catalog
    overlap) must never contribute toward eligibility, no matter how many
    words are shared — exactly the ef.com-on-alsaifgallery.com case."""
    result = assess_vertical_relevance(
        domain_tokens=set(), title_tokens={"منتجات", "صديقة", "للبيئة", "أثناء", "السفر"},
        real_catalog_tokens={"أدوات", "منزلية", "كهربائية"},  # real catalog: home appliances
        intent_topic_tokens={"منتجات", "صديقة", "للبيئة"},  # this store also has an eco-friendly intent
        shared_intent_count=2,
    )
    assert result.is_eligible_for_direct is False


class TestCompetitorRelevanceGateEndToEnd:
    """Part R2-F3 end-to-end through classify_competitors_for_run — the
    Kaspersky/EF-Education/pharmacy-app shape confirmed across 3 of 4
    Round 2 stores: a domain reached via generic queries ('safe shopping')
    whose SERP snippet coincidentally shares only generic words with the
    store's catalog/intent vocabulary."""

    def test_generic_query_only_overlap_is_never_promoted_to_direct_competitor(self, session):
        store, run = _make_store_and_run(session)
        session.add(Category(store_id=store.id, name="أدوات منزلية"))
        session.commit()

        # Two generic, non-discovery-shaped intents (would be excluded by
        # Part R2-F2's quality gate before ever reaching this store's
        # accepted set in production — but classify_competitors_for_run
        # only reads whatever Intent rows exist, so this test proves R2-F3
        # holds independently, as its own defense-in-depth layer).
        intent_a = _make_stable_intent(session, store, "تسوق آمن")
        intent_b = _make_stable_intent(session, store, "شراء آمن")
        unrelated = _make_competitor(session, store, run, "security-software.example")

        for stable_intent, title in [
            (intent_a, "أفضل حلول أمان وحماية للتسوق الآمن عبر الإنترنت"),
            (intent_b, "برنامج حماية وأمان شامل لتصفح آمن"),
        ]:
            session.add(
                SerpObservation(
                    store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    keyword_id=uuid.uuid4(), research_run_id=run.id, country="sa", language="ar",
                    results=[{"rank": 1, "domain": "security-software.example", "url": "https://security-software.example/x", "title": title}],
                )
            )
            session.add(
                CompetitorRelationship(
                    competitor_id=unrelated.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
                )
            )
        session.commit()

        classify_competitors_for_run(session, store.id, run.id)

        session.refresh(unrelated)
        assert unrelated.classification != "direct_competitor"
        assert is_business_competitor(unrelated) is False

    def test_genuine_competitor_with_specific_catalog_overlap_still_promoted(self, session):
        """Regression guard: the tightened gate must not collateral-damage
        real competitors — a rival with multiple *specific* shared catalog
        words across enough intents still becomes direct_competitor."""
        store, run = _make_store_and_run(session)
        session.add(Category(store_id=store.id, name="أدوات منزلية كهربائية"))
        session.commit()

        intent_a = _make_stable_intent(session, store, "أدوات منزلية")
        intent_b = _make_stable_intent(session, store, "أجهزة كهربائية")
        rival = _make_competitor(session, store, run, "home-appliances-rival.example")

        for stable_intent, title in [
            (intent_a, "أفضل أدوات منزلية كهربائية بأسعار مناسبة"),
            (intent_b, "أجهزة كهربائية منزلية للمطبخ"),
        ]:
            session.add(
                SerpObservation(
                    store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    keyword_id=uuid.uuid4(), research_run_id=run.id, country="sa", language="ar",
                    results=[{"rank": 1, "domain": "home-appliances-rival.example", "url": "https://home-appliances-rival.example/x", "title": title}],
                )
            )
            session.add(
                CompetitorRelationship(
                    competitor_id=rival.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
                )
            )
        session.commit()

        classify_competitors_for_run(session, store.id, run.id)

        session.refresh(rival)
        assert rival.classification == "direct_competitor"
        assert is_business_competitor(rival) is True

    def test_wikipedia_still_never_promoted_regardless_of_relevance_gate(self, session):
        """The curated-domain path (classify_known_domain) runs BEFORE the
        relevance gate and short-circuits it entirely — confirms R2-F3
        didn't accidentally weaken the R3 Wikipedia-never-a-competitor
        guarantee."""
        store, run = _make_store_and_run(session)
        session.add(Category(store_id=store.id, name="قهوة مختصة"))
        session.commit()
        intent_a = _make_stable_intent(session, store, "قهوة مختصة")
        intent_b = _make_stable_intent(session, store, "قهوة عربية")
        wiki = _make_competitor(session, store, run, "ar.wikipedia.org")

        for stable_intent in (intent_a, intent_b):
            session.add(
                SerpObservation(
                    store_id=store.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    keyword_id=uuid.uuid4(), research_run_id=run.id, country="sa", language="ar",
                    results=[{"rank": 1, "domain": "ar.wikipedia.org", "url": "https://ar.wikipedia.org/x", "title": "قهوة مختصة - ويكيبيديا"}],
                )
            )
            session.add(
                CompetitorRelationship(
                    competitor_id=wiki.id, intent_id=uuid.uuid4(), stable_intent_id=stable_intent.id,
                    research_run_id=run.id, source=RelationshipSource.serp, rank_or_position=1,
                )
            )
        session.commit()

        classify_competitors_for_run(session, store.id, run.id)

        session.refresh(wiki)
        assert wiki.classification == "publisher"
        assert is_business_competitor(wiki) is False
