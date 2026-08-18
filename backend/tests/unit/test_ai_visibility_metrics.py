import uuid

from app.ai_visibility.metrics import compute_ai_visibility_metrics
from app.models.ai_visibility import AIVisibilityObservation


def _obs(
    *,
    research_run_id,
    intent_id,
    prompt_variant_id,
    provider="openai",
    model="gpt-4o-mini",
    repetition_index=0,
    mentioned,
    citations=None,
    linked_domains=None,
):
    return AIVisibilityObservation(
        store_id=uuid.uuid4(),
        intent_id=intent_id,
        prompt_variant_id=prompt_variant_id,
        research_run_id=research_run_id,
        provider=provider,
        model=model,
        country="sa",
        language="ar",
        repetition_index=repetition_index,
        mentioned=mentioned,
        citations=citations or [],
        linked_domains=linked_domains or [],
    )


def test_returns_zeroed_metrics_with_no_observations(session):
    metrics = compute_ai_visibility_metrics(session, uuid.uuid4())
    assert metrics.total_observations == 0
    assert metrics.mention_rate == 0.0


def test_mention_rate_and_intent_coverage(session):
    run_id = uuid.uuid4()
    intent_a, intent_b = uuid.uuid4(), uuid.uuid4()
    variant = uuid.uuid4()

    rows = [
        _obs(research_run_id=run_id, intent_id=intent_a, prompt_variant_id=variant, mentioned=True),
        _obs(research_run_id=run_id, intent_id=intent_a, prompt_variant_id=variant, mentioned=False),
        _obs(research_run_id=run_id, intent_id=intent_b, prompt_variant_id=variant, mentioned=False),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    metrics = compute_ai_visibility_metrics(session, run_id)

    assert metrics.total_observations == 3
    assert metrics.mention_rate == 1 / 3
    assert metrics.intent_coverage == 1 / 2  # only intent_a had a mention


def test_citation_rate_denominator_is_answers_with_any_citation(session):
    run_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    variant = uuid.uuid4()

    rows = [
        _obs(
            research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, mentioned=True,
            citations=["https://roastinghouse.sa/x"], linked_domains=["roastinghouse.sa"],
        ),
        _obs(
            research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, mentioned=False,
            citations=["https://competitor.example/y"], linked_domains=[],
        ),
        _obs(research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, mentioned=False),  # no citations at all
    ]
    for r in rows:
        session.add(r)
    session.commit()

    metrics = compute_ai_visibility_metrics(session, run_id)

    # 2 answers had *some* citation; 1 of those cited the client -> 0.5
    assert metrics.citation_rate == 0.5


def test_stability_is_perfect_when_repetitions_agree(session):
    run_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    variant = uuid.uuid4()

    rows = [
        _obs(research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, repetition_index=0, mentioned=True),
        _obs(research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, repetition_index=1, mentioned=True),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    metrics = compute_ai_visibility_metrics(session, run_id)
    assert metrics.stability == 1.0


def test_stability_drops_when_repetitions_disagree(session):
    run_id = uuid.uuid4()
    intent_id = uuid.uuid4()
    variant = uuid.uuid4()

    rows = [
        _obs(research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, repetition_index=0, mentioned=True),
        _obs(research_run_id=run_id, intent_id=intent_id, prompt_variant_id=variant, repetition_index=1, mentioned=False),
    ]
    for r in rows:
        session.add(r)
    session.commit()

    metrics = compute_ai_visibility_metrics(session, run_id)
    assert metrics.stability == 0.5  # 1 out of 2 agrees with the majority (a tie here)
