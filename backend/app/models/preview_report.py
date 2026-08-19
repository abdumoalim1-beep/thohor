"""New MVP-scope, deliberately isolated from the existing VisibilityRun/
EngineAnswer/multi_engine_runner pipeline — that system's per-row commits,
multi-phase concurrency, and stage-machine races were the direct source of
the live bugs found and fixed earlier this session. This is the opposite
design on purpose: one background job builds one complete report entirely
in memory, then writes it as a single atomic row. There is no intermediate
state for a client to observe or race against — status is only ever
processing -> ready or processing -> failed.

report (PortableJSONB) holds the entire snapshot the frontend consumes —
store identity, visibility scores, competitors, every query result, and
the one recommendation — so every report screen after "ready" reads from
this one blob with zero further API calls, per the explicit requirement
that nothing between report screens may trigger new loading."""

import uuid
from datetime import datetime

from sqlalchemy import Column
from sqlmodel import Field

from app.core.db_types import PortableJSONB
from app.models.base import TimestampedModel


class PreviewReport(TimestampedModel, table=True):
    __tablename__ = "preview_reports"

    store_url: str
    # processing|ready|failed — the only three values the API ever returns.
    status: str = Field(default="processing", index=True)
    # Finer-grained internal stage for observability/debugging only (see
    # PREVIEW_STAGES) — never surfaced to the frontend, which manages no
    # pipeline of its own.
    stage: str | None = None
    error_message: str | None = None
    report: dict | None = Field(default=None, sa_column=Column(PortableJSONB))
    completed_at: datetime | None = None
    # Abuse guard (spec follow-up) — the real client IP (see
    # app.api.preview_reports._client_ip), used to reject a second report
    # from the same address within PREVIEW_REPORT_IP_COOLDOWN_HOURS. Never
    # shown to the client, only read back for that one check.
    ip_address: str | None = Field(default=None, index=True)


class PreviewReportLead(TimestampedModel, table=True):
    """A real join-trial request submitted from a preview report's beta
    modal (spec Stage 11/12) — kept as its own small table (mirroring
    OnboardingLead's shape) rather than extending OnboardingLead itself,
    since that model's store_id FK is required and tied to the existing
    Store/ResearchRun pipeline this system deliberately doesn't create
    rows in. report_feedback/interest_level are the two required survey
    answers captured alongside contact details — free-text slugs rather
    than an enum column since this is a one-shot MVP signal, not a
    CRM-integrated field."""

    __tablename__ = "preview_report_leads"

    preview_report_id: uuid.UUID = Field(foreign_key="preview_reports.id", index=True)
    name: str
    email: str
    report_feedback: str
    interest_level: str
