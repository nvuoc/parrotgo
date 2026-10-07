"""Pytest fixtures and configuration."""

import pytest
from src.db.sqlite_manager import SQLiteManager
from src.db.in_memory_cache import GeoCache
from src.db.chroma_client import ChromaFAQClient


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_parrotgo.db"
    return SQLiteManager(db_path=str(db_file))


@pytest.fixture
def fresh_geo_cache():
    return GeoCache()


@pytest.fixture
def empty_faq_client(tmp_path):
    chroma_dir = tmp_path / "test_chroma"
    return ChromaFAQClient(data_dir=str(chroma_dir))


@pytest.fixture(autouse=True)
def force_mock_mode_in_tests(tmp_path, monkeypatch):
    """Ensure unit tests run deterministically offline without consuming external API credits."""
    from src.config import settings
    from src.services.vietmap_client import vietmap_client

    monkeypatch.setattr(settings, "GEO_DATA_PATH", str(tmp_path / "places_snapshot.json"))
    prev_map = settings.MAP_MODE
    prev_llm = settings.LLM_MODE
    prev_vm_mode = vietmap_client.mode

    settings.MAP_MODE = "mock"
    settings.LLM_MODE = "mock"
    vietmap_client.mode = "mock"

    yield

    settings.MAP_MODE = prev_map
    settings.LLM_MODE = prev_llm
    vietmap_client.mode = prev_vm_mode
