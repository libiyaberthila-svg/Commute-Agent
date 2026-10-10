import pytest
from backend.database import init_db

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    init_db()
