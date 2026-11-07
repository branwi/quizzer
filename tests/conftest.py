import pytest
from sqlalchemy.orm import Session

from app.database import create_tables, make_engine
from scripts.seed import seed


@pytest.fixture
def engine():
    engine = make_engine("sqlite:///:memory:")
    create_tables(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def seeded(db):
    with db.begin():
        seed(db)
    return db
