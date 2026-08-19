"""API surface for PreviewReport — deliberately separate from
app/api/stores.py and the rest of the /signup surface: no store_id, no
ResearchRun, nothing shared with that pipeline. Three endpoints only, per
spec: create (kicks off the one background job), poll (processing/ready/
failed — nothing more granular ever reaches the client), and submit a
beta-trial lead once the merchant has seen their report."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.core.db import get_session
from app.models.preview_report import PreviewReport, PreviewReportLead
from app.workers.tasks import execute_preview_report_task

router = APIRouter(prefix="/preview-reports", tags=["preview-reports"])


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


@router.post("", response_model=CreatePreviewReportResponse)
def create_preview_report(
    payload: CreatePreviewReportRequest, session: Session = Depends(get_session)
) -> CreatePreviewReportResponse:
    from app.workers.tasks import execute_preview_report_task  # deferred: avoids a celery/app.main import cycle

    store_url = payload.store_url.strip()
    if not store_url:
        raise HTTPException(status_code=422, detail="store_url is required")
    if not store_url.startswith(("http://", "https://")):
        store_url = f"https://{store_url}"

    report = PreviewReport(store_url=store_url, status="processing")
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
