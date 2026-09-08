import os

import pytest
from app.config import get_settings
from app.main import _sorted_volume_map


@pytest.fixture(autouse=True, scope="session")
def test_db(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("data") / "test.db")
    os.environ["DB_PATH"] = db_path
    get_settings.cache_clear()
    # Derived from Settings — must be cleared alongside it or VOLUME_MAP leaks.
    _sorted_volume_map.cache_clear()
    yield
    os.environ.pop("DB_PATH", None)
    get_settings.cache_clear()
    _sorted_volume_map.cache_clear()
