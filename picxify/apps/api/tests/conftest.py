from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.auth import Principal, get_principal
from app.db import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def _fresh_schema() -> Generator[None, None, None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client() -> TestClient:
    def override_get_db() -> Generator:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


@pytest.fixture
def as_user(client: TestClient):
    """Authenticate the test client as a given principal, bypassing JWT verification."""

    def _as(
        auth_user_id: str = "user_test_1",
        email: str = "test1@example.com",
        name: str | None = "Test User",
    ) -> TestClient:
        app.dependency_overrides[get_principal] = lambda: Principal(
            auth_user_id=auth_user_id, email=email, name=name
        )
        return client

    return _as
