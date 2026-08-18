"""backfill measurement baseline stable intent keys

Revision ID: 1c522554b6c4
Revises: b5ad349b120b
Create Date: 2026-08-11 21:54:48.539438

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '1c522554b6c4'
down_revision: Union[str, None] = 'b5ad349b120b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Data-only fix, no schema change. The ebd428887178 migration (Part
    F.5-0) backfilled Recommendation.target_intents from Intent ids to
    StableIntent ids, but missed the same JSONB shape one level down:
    MeasurementBaseline.target_queries/target_prompts rows captured before
    F.5-0 still carry the key 'intent_id' (a run-scoped id, useless across
    runs) instead of 'stable_intent_id'. app.measurement.control_set relies
    on 'stable_intent_id' being present to re-issue the Control Set on a
    later run — without this, monitoring silently KeyErrors on every
    pre-F.5-0 baseline. Adds the new key alongside the old one; nothing is
    removed."""
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, target_queries, target_prompts FROM measurement_baselines")).fetchall()

    intent_to_stable_cache: dict[str, str | None] = {}

    def resolve_stable_id(intent_id: str) -> str | None:
        if intent_id not in intent_to_stable_cache:
            result = conn.execute(
                sa.text("SELECT stable_intent_id FROM intents WHERE id = :intent_id"), {"intent_id": intent_id}
            ).first()
            intent_to_stable_cache[intent_id] = str(result[0]) if result and result[0] else None
        return intent_to_stable_cache[intent_id]

    update_stmt = sa.text(
        "UPDATE measurement_baselines SET target_queries = CAST(:tq AS jsonb), target_prompts = CAST(:tp AS jsonb) "
        "WHERE id = :id"
    )

    for row in rows:
        changed = False

        new_target_queries = []
        for item in row.target_queries or []:
            item = dict(item)
            if "intent_id" in item and "stable_intent_id" not in item:
                stable_id = resolve_stable_id(item["intent_id"])
                if stable_id:
                    item["stable_intent_id"] = stable_id
                    changed = True
            new_target_queries.append(item)

        new_target_prompts = []
        for item in row.target_prompts or []:
            item = dict(item)
            if "intent_id" in item and "stable_intent_id" not in item:
                stable_id = resolve_stable_id(item["intent_id"])
                if stable_id:
                    item["stable_intent_id"] = stable_id
                    changed = True
            new_target_prompts.append(item)

        if changed:
            conn.execute(
                update_stmt,
                {"tq": json.dumps(new_target_queries), "tp": json.dumps(new_target_prompts), "id": row.id},
            )


def downgrade() -> None:
    pass
