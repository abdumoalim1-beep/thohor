"""Regression test for a real bug caught during live verification: the
trigger endpoint used to pre-create a VisibilityRun to return its id, but
run_visibility_run created a second, disconnected one internally — the
first stayed stuck at status="running" forever and the id handed back to
the caller pointed at a row that never actually ran anything. Confirms
run_visibility_run operates on the exact row it's given, never a new one."""

from app.ai_visibility.multi_engine_runner import create_pending_visibility_run, run_visibility_run
from app.models.org import Organization
from app.models.store import Store
from app.providers.ai.base import AIProvider, AIRequest, AIResponse, AIUsage
from app.providers.ai.router import ModelRouter


class _NoOpProvider(AIProvider):
    name = "openai"

    async def generate(self, request: AIRequest) -> AIResponse:
        return AIResponse(provider=self.name, model=request.model, text="answer", usage=AIUsage())


async def test_run_visibility_run_operates_on_the_given_row_never_creates_another(session):
    org = Organization(name="t", slug="t-run-identity")
    session.add(org)
    session.commit()
    session.refresh(org)
    store = Store(organization_id=org.id, url="https://flowery.example")
    session.add(store)
    session.commit()
    session.refresh(store)

    pending = create_pending_visibility_run(session, store.id)
    router = ModelRouter(providers={"openai": _NoOpProvider()}, routes={})

    result = await run_visibility_run(session=session, router=router, run=pending)

    # Same row, updated in place — not a different id.
    assert result.id == pending.id
    assert result.status == "completed"
    assert result.completed_at is not None
