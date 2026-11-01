import pytest

from app.data.loader import load_data


@pytest.fixture(scope="session")
def store():
    return load_data()
