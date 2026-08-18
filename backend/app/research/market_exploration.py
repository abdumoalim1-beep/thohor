from urllib.parse import urlparse

from sqlmodel import Session, select

from app.models.competitor import Competitor
from app.models.intent import Intent
from app.models.store import Store


def exploration_queries(session: Session, store: Store, topic: str, max_queries: int) -> list[str]:
    """Expand only from already-discovered store intents. No invented volume,
    keywords or paid-provider call is needed before the user starts."""
    normalized = topic.strip()
    candidates = session.exec(
        select(Intent)
        .where(Intent.store_id == store.id)
        .order_by(Intent.confidence.desc())  # type: ignore[arg-type]
    ).all()
    related = [
        intent.topic for intent in candidates
        if intent.topic != normalized and (
            normalized.casefold() in intent.topic.casefold()
            or intent.topic.casefold() in normalized.casefold()
            or (intent.category and intent.category.casefold() in normalized.casefold())
        )
    ]
    queries = [normalized, *related]
    return list(dict.fromkeys(queries))[:max_queries]


def store_domain(store: Store) -> str:
    return (urlparse(store.url).hostname or "").removeprefix("www.").casefold()


def classify_result_domain(session: Session, store: Store, domain: str) -> str:
    normalized = domain.removeprefix("www.").casefold()
    if normalized == store_domain(store) or normalized.endswith(f".{store_domain(store)}"):
        return "store"
    competitor = session.exec(
        select(Competitor)
        .where(Competitor.store_id == store.id)
        .where(Competitor.domain == normalized)
    ).first()
    if competitor is None:
        return "unclassified_source"
    return competitor.classification or competitor.competitor_type.value

