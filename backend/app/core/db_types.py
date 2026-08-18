from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# Real JSONB in Postgres (production/dev); falls back to generic JSON on
# SQLite so the unit test suite can run against an in-memory DB with no
# Docker/Postgres dependency, per the "unit tests must not need network or
# external services" rule. Integration tests still run against real Postgres.
PortableJSONB = JSONB().with_variant(JSON(), "sqlite")
