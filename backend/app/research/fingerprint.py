import hashlib
import uuid

from app.models.research_task import TaskType


def compute_task_fingerprint(task_type: TaskType, target: str, locale: str, research_run_id: uuid.UUID) -> str:
    """Dedup key for a proposed task: same task_type + normalized target +
    locale within the same research_run is considered 'already asked' (PRD
    Group D2 design decision #7) — scoped to research_run_id, not the store
    globally, since cross-run dedup is a documented future enhancement, not
    a V1 requirement."""
    normalized_target = " ".join(target.strip().lower().split())
    raw = f"{task_type.value}|{normalized_target}|{locale}|{research_run_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
