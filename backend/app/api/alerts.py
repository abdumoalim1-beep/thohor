import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.schemas import AlertItem, UpdateAlertStatusRequest
from app.core.db import get_session
from app.models.alert import Alert, AlertStatus

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.patch("/{alert_id}/status", response_model=AlertItem)
def update_alert_status(
    alert_id: uuid.UUID, payload: UpdateAlertStatusRequest, session: Session = Depends(get_session)
) -> AlertItem:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")

    try:
        alert.status = AlertStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid status '{payload.status}'")

    session.add(alert)
    session.commit()
    session.refresh(alert)

    return AlertItem(
        id=alert.id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        message=alert.message,
        status=alert.status.value,
        related_recommendation_id=alert.related_recommendation_id,
        related_competitor_id=alert.related_competitor_id,
        created_at=alert.created_at.isoformat(),
    )
