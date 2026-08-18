import json

from sqlmodel import select

from app.crawler.fetch import FetchResult
from app.crawler.security import CrawlSecurityPolicy
from app.intent.intent_engine import _attach_keywords
from app.models.competitor import Competitor, CompetitorRelationship, CompetitorType, RelationshipSource
from app.models.evidence import Evidence, EvidenceSourceType
from app.models.intent import Intent, IntentSource
from app.models.org import Organization
from app.models.page_intelligence import PageGapAnalysis
from app.models.research import ResearchRun
from app.models.serp import SerpObservation
from app.models.store import Store
from app.page_intelligence import gap_engine as gap_engine_module
from app.page_intelligence.gap_engine import run_page_intelligence_agent
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute

COMPETITOR_HTML = (
    "<html><head><title>Best Coffee Grinder Guide</title>"
    '<meta name="description" content="Full buying guide with shipping info">'
    "</head><body><h1>Best Coffee Grinder Guide</h1></body></html>"
)


class FakeGapProvider(AIProvider):
    name = "fake_gap"

    async def generate(self, request: AIRequest) -> AIResponse:
        payload = json.dumps(
            {
                "gaps": ["دليل شامل للشراء غير موجود عندنا", "لا يوجد معلومات شحن مفصلة"],
                "recommendation_summary": "أضف دليل شراء ومعلومات شحن للصفحة.",
                "confidence": 0.75,
            }
        )
        return AIResponse(
            provider=self.name, model=request.model, text=payload, usage=AIUsage(input_tokens=20, output_tokens=20)
        )


class FakeStorage:
    def put_text(self, key_prefix: str, content: str, content_type: str = "text/html") -> str:
        return f"s3://fake-bucket/{key_prefix}/fake-key"


def _make_scenario(session):
    org = Organization(name="t", slug="t-gap-engine")
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

    weak_intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="coffee grinder",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    strong_intent = Intent(
        store_id=store.id,
        research_run_id=run.id,
        topic="espresso machine",
        country="sa",
        language="ar",
        source=IntentSource.deterministic_catalog,
    )
    session.add(weak_intent)
    session.add(strong_intent)
    session.commit()
    session.refresh(weak_intent)
    session.refresh(strong_intent)
    _attach_keywords(session, weak_intent, ["coffee grinder"], "sa", "ar")
    _attach_keywords(session, strong_intent, ["espresso machine"], "sa", "ar")

    competitor = Competitor(
        store_id=store.id,
        domain="rival.test",
        name="rival.test",
        competitor_type=CompetitorType.search_competitor,
        first_seen_research_run_id=run.id,
    )
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    from app.models.intent import IntentKeyword, Keyword

    weak_keyword = session.exec(
        select(Keyword).join(IntentKeyword, IntentKeyword.keyword_id == Keyword.id).where(
            IntentKeyword.intent_id == weak_intent.id
        )
    ).first()
    strong_keyword = session.exec(
        select(Keyword).join(IntentKeyword, IntentKeyword.keyword_id == Keyword.id).where(
            IntentKeyword.intent_id == strong_intent.id
        )
    ).first()

    # weak_intent: we're absent (client_rank None), rival is #1
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=weak_intent.id,
            keyword_id=weak_keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[
                {"rank": 1, "domain": "rival.test", "url": "https://rival.test/grinders"},
                {"rank": 2, "domain": "store.example", "url": "https://store.example/grinders"},
            ],
            client_rank=None,
            client_url=None,
        )
    )
    # strong_intent: we already rank #1, should NOT become a gap candidate
    session.add(
        SerpObservation(
            store_id=store.id,
            intent_id=strong_intent.id,
            keyword_id=strong_keyword.id,
            research_run_id=run.id,
            country="sa",
            language="ar",
            results=[{"rank": 1, "domain": "store.example", "url": "https://store.example/espresso"}],
            client_rank=1,
            client_url="https://store.example/espresso",
        )
    )
    session.commit()

    session.add(
        CompetitorRelationship(
            competitor_id=competitor.id,
            intent_id=weak_intent.id,
            research_run_id=run.id,
            source=RelationshipSource.serp,
            rank_or_position=1,
        )
    )
    session.commit()

    return store, run, weak_intent, competitor


async def test_run_page_intelligence_agent_produces_analysis_for_weak_intent(session, monkeypatch):
    store, run, weak_intent, competitor = _make_scenario(session)

    async def fake_safe_fetch(url, policy):
        assert url == "https://rival.test/grinders"
        return FetchResult(url=url, status_code=200, content_type="text/html", text=COMPETITOR_HTML)

    monkeypatch.setattr(gap_engine_module, "safe_fetch", fake_safe_fetch)

    router = ModelRouter(
        providers={"fake": FakeGapProvider()},
        routes={"page_gap_analysis": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )
    policy = CrawlSecurityPolicy(max_response_bytes=1_000_000, request_timeout_seconds=5, user_agent="TestBot/1.0")

    analyses = await run_page_intelligence_agent(
        session=session,
        router=router,
        storage=FakeStorage(),
        store_id=store.id,
        research_run_id=run.id,
        agent_run_id=None,
        max_gaps=3,
        crawl_policy=policy,
    )

    assert len(analyses) == 1
    analysis = analyses[0]
    assert analysis.intent_id == weak_intent.id
    assert analysis.competitor_id == competitor.id
    assert analysis.competitor_url == "https://rival.test/grinders"
    assert "دليل شامل للشراء غير موجود عندنا" in analysis.gaps
    assert analysis.confidence == 0.75

    persisted = session.exec(select(PageGapAnalysis).where(PageGapAnalysis.research_run_id == run.id)).all()
    assert len(persisted) == 1

    evidence = session.exec(select(Evidence).where(Evidence.source_type == EvidenceSourceType.page_gap_analysis)).all()
    assert len(evidence) == 1
    assert evidence[0].source_id == analysis.id
