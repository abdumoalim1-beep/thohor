import uuid

from sqlalchemy.orm import defer
from sqlmodel import Session, select

from app.models.evidence import Evidence
from app.models.finding import Finding
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation


def trace_recommendation_evidence(session: Session, recommendation_id: uuid.UUID) -> dict | None:
    """Walks Recommendation -> Opportunity -> Findings -> Evidence, so the
    product can answer 'why did you tell me to do this?' (Group E5) without
    a new storage layer — everything needed is already linked via the
    evidence_ids/finding_ids captured when the Opportunity was discovered
    (Part E1) and copied onto the Recommendation (Part E3)."""
    recommendation = session.exec(
        select(Recommendation)
        .options(defer(Recommendation.page_id), defer(Recommendation.product_id))
        .where(Recommendation.id == recommendation_id)
    ).first()
    if recommendation is None:
        return None

    opportunity = session.get(Opportunity, recommendation.opportunity_id)

    findings = []
    if opportunity is not None:
        for finding_id in opportunity.finding_ids:
            finding = session.get(Finding, uuid.UUID(finding_id))
            if finding is not None:
                findings.append(finding)

    evidence_rows = []
    for evidence_id in recommendation.evidence_ids:
        evidence = session.get(Evidence, uuid.UUID(evidence_id))
        if evidence is not None:
            evidence_rows.append(evidence)

    return {
        "recommendation": recommendation,
        "opportunity": opportunity,
        "findings": findings,
        "evidence": evidence_rows,
    }
