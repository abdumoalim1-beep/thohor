import uuid

from sqlmodel import Session

from app.models.intent import Intent
from app.models.intent_cluster import IntentCluster
from app.models.stable_intent import normalize_topic

# Part Q1 — deliberately lower than app.intent.quality's
# NEAR_DUPLICATE_JACCARD_THRESHOLD (0.6, which rejects near-identical
# phrasings of the *same* question). This threshold groups genuinely
# distinct but topically-related intents ('قهوة مختصة' + 'معدات تحضير
# القهوة المختصة') without merging unrelated ones that merely share a
# category.
CLUSTER_JACCARD_THRESHOLD = 0.25

UNCATEGORIZED_LABEL = "بدون تصنيف"

# Same stopword list / token rule as app.intent.quality._content_tokens —
# duplicated rather than imported, matching this project's existing
# precedent (app.competitors.classification keeps its own independent copy
# of the same small helper rather than cross-importing a "private"
# underscored function between modules).
_ARABIC_STOPWORDS = {
    "من", "في", "على", "الى", "إلى", "و", "أو", "او", "ما", "هو", "هي", "وش", "ايش", "أي",
    "لي", "لك", "عن", "مع", "هذا", "هذه", "التي", "الذي", "يا",
}


def _content_tokens(text: str) -> set[str]:
    normalized = normalize_topic(text)
    return {t for t in normalized.split() if t not in _ARABIC_STOPWORDS and len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_intents(
    session: Session, store_id: uuid.UUID, research_run_id: uuid.UUID, intents: list[Intent]
) -> list[IntentCluster]:
    """Groups this run's *accepted* intents (rejected ones never cluster)
    into IntentCluster rows: first by category (deterministic, already on
    the row), then within each category by content-token Jaccard overlap
    — no AI call, no new cost. Every accepted intent ends up in exactly
    one cluster, including clusters of size 1 (a genuinely standalone
    topic is still a topic, not a missing cluster). Mutates each accepted
    Intent's cluster_id and persists the new IntentCluster rows.
    """
    accepted = [i for i in intents if i.is_accepted]
    if not accepted:
        return []

    by_category: dict[str, list[Intent]] = {}
    for intent in accepted:
        by_category.setdefault(intent.category or UNCATEGORIZED_LABEL, []).append(intent)

    clusters: list[IntentCluster] = []
    for category, group in by_category.items():
        # Highest quality_score first — mirrors app.intent.quality's own
        # near-duplicate dedup logic, so the cluster's representative
        # label is always the best-quality member, never an arbitrary one.
        ordered = sorted(group, key=lambda i: i.quality_score, reverse=True)
        cluster_members: list[list[Intent]] = []
        cluster_tokens: list[set[str]] = []

        for intent in ordered:
            tokens = _content_tokens(intent.topic)
            joined = False
            for idx, ref_tokens in enumerate(cluster_tokens):
                if _jaccard(tokens, ref_tokens) >= CLUSTER_JACCARD_THRESHOLD:
                    cluster_members[idx].append(intent)
                    joined = True
                    break
            if not joined:
                cluster_members.append([intent])
                cluster_tokens.append(tokens)

        for members in cluster_members:
            representative = members[0]  # already sorted by quality_score desc
            cluster = IntentCluster(
                store_id=store_id,
                research_run_id=research_run_id,
                label=representative.topic,
                category=None if category == UNCATEGORIZED_LABEL else category,
                intent_count=len(members),
            )
            session.add(cluster)
            session.commit()
            session.refresh(cluster)

            for member in members:
                member.cluster_id = cluster.id
                session.add(member)
            session.commit()

            clusters.append(cluster)

    return clusters
