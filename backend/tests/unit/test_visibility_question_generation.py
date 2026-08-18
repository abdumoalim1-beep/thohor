"""Phase 7 / SIGNUP re-scope — generate_visibility_questions against a fake
AIProvider. One AI call per category now (not one big call for all 9) — the
fake provider looks at which category the rendered prompt actually asked
for and answers accordingly, mirroring the real per-category design.
Covers: questions from multiple categories all persist and are stamped
with the category actually requested (never the AI's own echoed value —
that's what makes an 'unknown category' leak structurally impossible now),
re-running doesn't duplicate (normalize_topic dedup), and one category's
provider call failing doesn't block the others or raise."""

import itertools
import json

from sqlmodel import select

from app.ai_visibility.question_generation import generate_visibility_questions
from app.models.org import Organization
from app.models.research import ResearchRun
from app.models.store import Store
from app.models.visibility_run import VisibilityQuestion
from app.providers.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse, AIRole, AIUsage
from app.providers.ai.router import ModelChoice, ModelRouter, TaskRoute
from app.schemas.store_identity import StoreIdentity
from app.schemas.visibility_question import QUESTION_CATEGORIES


class FakeQuestionProvider(AIProvider):
    """Answers per-category — inspects the rendered prompt's embedded
    category_key (the same text app.prompts.visibility_question_generation
    renders it into) to decide which canned response to return, exactly
    like a real model would condition its answer on the category it was
    actually asked to generate for."""

    name = "fake_questions"

    def __init__(self, questions_by_category: dict[str, list[dict]] | None = None, raise_for: set[str] | None = None):
        self._questions_by_category = questions_by_category or {}
        self._raise_for = raise_for or set()

    async def generate(self, request: AIRequest) -> AIResponse:
        user_content = next((m.content for m in request.messages if m.role == AIRole.user), "")
        category = next((cat for cat in self._questions_by_category if f'"{cat}"' in user_content), None)
        if category is None:
            category = next((cat for cat in self._raise_for if f'"{cat}"' in user_content), None)
        if category in self._raise_for:
            raise AIProviderError("provider unavailable")
        questions = self._questions_by_category.get(category, [])
        return AIResponse(
            provider=self.name, model=request.model, text=json.dumps({"questions": questions}),
            usage=AIUsage(input_tokens=10, output_tokens=10),
        )


def _make_store(session):
    org = Organization(name="t", slug="t-questions")
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


def _router(provider: AIProvider) -> ModelRouter:
    return ModelRouter(
        providers={"fake": provider},
        routes={"visibility_question_generation": TaskRoute(primary=ModelChoice("fake", "fake-model"))},
    )


_IDENTITY = StoreIdentity(brand_name="فلاوري", business_type="متجر ورد", categories=["ورد"], confidence=0.9)


async def test_questions_from_multiple_categories_all_persist(session):
    store, run = _make_store(session)
    provider = FakeQuestionProvider({
        "best": [{"text": "ما أفضل متجر ورد؟", "category": "best"}],
        "alternatives": [
            {"text": "أبحث عن بديل لمتجر معروف للورد", "category": "alternatives"},
            {"text": "ما هي البدائل المتاحة لهدايا الورد؟", "category": "alternatives"},
        ],
    })

    persisted, evidence_ids = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=["منافس"],
    )

    assert len(persisted) == 3
    assert len(evidence_ids) == 9  # one evidence row per category call, including the empty ones
    assert {q.category for q in persisted} == {"best", "alternatives"}


async def test_question_is_stamped_with_the_requested_category_not_the_ais_own_field(session):
    """The model might echo back a wrong/nonsensical category field — this
    can never leak through anymore, since the category is forced from
    which prompt was actually sent, not read from the AI's JSON."""
    store, run = _make_store(session)
    provider = FakeQuestionProvider({
        "price": [{"text": "كم سعر باقة الورد المتوسطة؟", "category": "totally_wrong_category"}],
    })

    persisted, _ = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    assert len(persisted) == 1
    assert persisted[0].category == "price"


async def test_rerun_does_not_duplicate_an_already_persisted_question(session):
    store, run = _make_store(session)
    provider = FakeQuestionProvider({"best": [{"text": "ما أفضل متجر ورد؟", "category": "best"}]})
    router = _router(provider)

    first, _ = await generate_visibility_questions(
        session=session, router=router, store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )
    assert len(first) == 1

    second, _ = await generate_visibility_questions(
        session=session, router=router, store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )
    assert second == []

    all_rows = session.exec(select(VisibilityQuestion).where(VisibilityQuestion.store_id == store.id)).all()
    assert len(all_rows) == 1


async def test_near_duplicate_punctuation_and_case_still_dedupes(session):
    store, run = _make_store(session)
    provider1 = FakeQuestionProvider({"best": [{"text": "ما أفضل متجر ورد؟", "category": "best"}]})
    await generate_visibility_questions(
        session=session, router=_router(provider1), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    provider2 = FakeQuestionProvider({"best": [{"text": "ما أفضل متجر ورد", "category": "best"}]})  # no trailing ؟
    second, _ = await generate_visibility_questions(
        session=session, router=_router(provider2), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )
    assert second == []


async def test_one_category_failing_never_blocks_the_others(session):
    store, run = _make_store(session)
    provider = FakeQuestionProvider(
        questions_by_category={"best": [{"text": "ما أفضل متجر ورد؟", "category": "best"}]},
        raise_for={"price"},
    )

    persisted, evidence_ids = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    assert len(persisted) == 1
    assert persisted[0].category == "best"
    assert len(evidence_ids) == 8  # 9 categories attempted, 1 (price) failed and got no evidence row


async def test_total_persisted_is_capped_at_target_even_with_a_larger_pool(session):
    """90-search re-scope: TARGET_TOTAL_QUESTIONS=60, not the earlier 135 —
    even if every category over-delivers, the aggregate must stay capped.
    Each generated text uses a genuinely distinct noun each time (not just
    a trailing digit, which the tokenizer's len>1 filter strips, making
    otherwise-identical texts collide with the near-duplicate guard)."""
    from app.ai_visibility.question_generation import TARGET_TOTAL_QUESTIONS

    # 63 pairwise-distinct single-token "words" (every 2-letter combination
    # from a 9-letter pool) each wrapped in a minimal one-word boilerplate —
    # verified (see this test's design notes) to keep every pairwise
    # Jaccard overlap at/under 0.5, safely below the near-duplicate
    # guard's 0.6 threshold, while every normalized text stays unique.
    letters = ["ب", "ت", "ث", "ج", "ح", "خ", "د", "ذ", "ر"]
    pseudo_words = ["".join(p) for p in itertools.product(letters, repeat=2)]
    categories_ordered = list(QUESTION_CATEGORIES)
    words_iter = iter(pseudo_words)
    provider = FakeQuestionProvider({
        category: [{"text": f"سؤال عن {next(words_iter)}", "category": category} for _ in range(7)]
        for category in categories_ordered
    })
    store, run = _make_store(session)

    persisted, _ = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    assert len(persisted) == TARGET_TOTAL_QUESTIONS


async def test_near_duplicate_paraphrase_across_categories_is_still_deduped(session):
    """normalize_topic's exact-match dedup wouldn't catch two differently-
    worded questions asking the same thing — the added Jaccard-overlap
    near-duplicate guard should."""
    provider = FakeQuestionProvider({
        "best": [{"text": "ما هو أفضل متجر لشراء الورد في الرياض", "category": "best"}],
        "recommendation": [{"text": "أفضل متجر لشراء الورد في مدينة الرياض", "category": "recommendation"}],
    })
    store, run = _make_store(session)

    persisted, _ = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    assert len(persisted) == 1


async def test_every_category_failing_degrades_to_empty_never_raises(session):
    store, run = _make_store(session)
    provider = FakeQuestionProvider(raise_for=set(QUESTION_CATEGORIES))

    persisted, evidence_ids = await generate_visibility_questions(
        session=session, router=_router(provider), store_id=store.id, research_run_id=run.id,
        agent_run_id=None, identity=_IDENTITY, competitor_names=[],
    )

    assert persisted == []
    assert evidence_ids == []
