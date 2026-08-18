import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — registers all tables on SQLModel.metadata


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
