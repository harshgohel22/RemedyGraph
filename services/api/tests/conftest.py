import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import create_db_engine, get_db
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def world_earbuds() -> dict:
    return json.loads((FIXTURES / "world_earbuds.json").read_text())


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_db_engine("sqlite://", static_memory=True)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator:
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app(init_db=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
