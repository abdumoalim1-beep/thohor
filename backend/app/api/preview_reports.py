"""API surface for PreviewReport — deliberately separate from
app/api/stores.py and the rest of the /signup surface: no store_id, no
ResearchRun, nothing shared with that pipeline. Three endpoints only, per
spec: create (kicks off the one background job), poll (processing/ready/
failed — nothing more granular ever reaches the client), and submit a
beta-trial lead once the merchant has seen their report."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.db import get_session
from app.models.preview_report import PreviewReport, PreviewReportLead
from app.workers.tasks import execute_preview_report_task

router = APIRouter(prefix="/preview-reports", tags=["preview-reports"])

# Abuse guard — each real search/AI run costs real money (see
# app.preview_reports.search), so one IP gets one report per this window
# rather than an unbounded number of free runs. A time window instead of a
# lifetime ban on purpose: a shared IP (office wifi, mobile carrier NAT)
# would otherwise permanently lock out every other real visitor behind it
# after the first one uses the tool once.
PREVIEW_REPORT_IP_COOLDOWN_HOURS = 48


def _client_ip(request: Request) -> str | None:
    """The app has no ProxyHeaders/TrustedHost middleware, so
    request.client.host is Render's own load-balancer IP in production, not
    the visitor's — every request arrives with the real IP as the first
    entry of X-Forwarded-For instead (set by Render's proxy, not spoofable
    by the client through it). Falls back to request.client.host for local
    dev, where there is no proxy and no such header."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


def _is_bypass(request: Request) -> bool:
    """Trusted callers (the site owner, testing repeatedly) skip the IP
    cooldown by sending X-Preview-Bypass matching
    settings.preview_report_bypass_token. Disabled by default — an unset
    token means no header value can ever match."""
    token = get_settings().preview_report_bypass_token
    if token is None:
        return False
    provided = request.headers.get("x-preview-bypass")
    return provided is not None and provided == token.get_secret_value()


class CreatePreviewReportRequest(BaseModel):
    store_url: str


class CreatePreviewReportResponse(BaseModel):
    report_id: uuid.UUID
    status: str


class PreviewReportResponse(BaseModel):
    id: uuid.UUID
    status: str
    report: dict | None = None
    error_message: str | None = None


class PreviewReportJoinRequest(BaseModel):
    name: str
    email: str
    report_feedback: str
    interest_level: str


class PreviewReportJoinResponse(BaseModel):
    id: uuid.UUID


def _validate_lead_payload(payload: PreviewReportJoinRequest) -> tuple[str, str, str, str]:
    name = payload.name.strip()
    email = payload.email.strip()
    report_feedback = payload.report_feedback.strip()
    interest_level = payload.interest_level.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if not email:
        raise HTTPException(status_code=422, detail="email is required")
    if not report_feedback:
        raise HTTPException(status_code=422, detail="report_feedback is required")
    if not interest_level:
        raise HTTPException(status_code=422, detail="interest_level is required")
    return name, email, report_feedback, interest_level


@router.post("", response_model=CreatePreviewReportResponse)
def create_preview_report(
    payload: CreatePreviewReportRequest, request: Request, session: Session = Depends(get_session)
) -> CreatePreviewReportResponse:
    from app.workers.tasks import execute_preview_report_task  # deferred: avoids a celery/app.main import cycle

    store_url = payload.store_url.strip()
    if not store_url:
        raise HTTPException(status_code=422, detail="store_url is required")
    if not store_url.startswith(("http://", "https://")):
        store_url = f"https://{store_url}"

    ip_address = _client_ip(request)
    if ip_address and not _is_bypass(request):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=PREVIEW_REPORT_IP_COOLDOWN_HOURS)
        recent = session.exec(
            select(PreviewReport)
            .where(PreviewReport.ip_address == ip_address, PreviewReport.created_at >= cutoff)
            .limit(1)
        ).first()
        if recent is not None:
            raise HTTPException(
                status_code=429,
                detail="تم استخدام تحليل مجاني من هذا الجهاز مؤخرًا — جرّب مرة أخرى بعد قليل",
            )

    report = PreviewReport(store_url=store_url, status="processing", ip_address=ip_address)
    session.add(report)
    session.commit()
    session.refresh(report)

    execute_preview_report_task.delay(str(report.id))
    return CreatePreviewReportResponse(report_id=report.id, status=report.status)


@router.get("/{report_id}", response_model=PreviewReportResponse)
def get_preview_report(report_id: uuid.UUID, session: Session = Depends(get_session)) -> PreviewReportResponse:
    report = session.get(PreviewReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="preview report not found")
    return PreviewReportResponse(
        id=report.id,
        status=report.status,
        report=report.report if report.status == "ready" else None,
        error_message=report.error_message if report.status == "failed" else None,
    )


@router.post("/{report_id}/join", response_model=PreviewReportJoinResponse)
def join_preview_report_beta(
    report_id: uuid.UUID, payload: PreviewReportJoinRequest, session: Session = Depends(get_session)
) -> PreviewReportJoinResponse:
    report = session.get(PreviewReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="preview report not found")

    name, email, report_feedback, interest_level = _validate_lead_payload(payload)
    lead = PreviewReportLead(
        preview_report_id=report_id,
        name=name,
        email=email,
        report_feedback=report_feedback,
        interest_level=interest_level,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return PreviewReportJoinResponse(id=lead.id)


@router.post("/leads", response_model=PreviewReportJoinResponse)
def join_beta_directly(
    payload: PreviewReportJoinRequest, session: Session = Depends(get_session)
) -> PreviewReportJoinResponse:
    """The header's "انضم للنسخة التجريبية" button opens the same beta
    modal with no prior analysis — same lead shape, preview_report_id is
    just None here since there's no report to attach to (see
    PreviewReportLead's docstring)."""
    name, email, report_feedback, interest_level = _validate_lead_payload(payload)
    lead = PreviewReportLead(
        preview_report_id=None,
        name=name,
        email=email,
        report_feedback=report_feedback,
        interest_level=interest_level,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return PreviewReportJoinResponse(id=lead.id)
