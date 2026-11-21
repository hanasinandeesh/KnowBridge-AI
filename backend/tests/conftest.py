import os
import pytest
from fastapi.testclient import TestClient

# Flag to avoid live network probes during automated testing
os.environ["TESTING"] = "1"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Provides a reusable FastAPI TestClient instance."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
