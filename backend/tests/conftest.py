import os
import tempfile
from pathlib import Path

# Must run before any app import reads settings: tests use a throwaway SQLite DB and never the network.
_tmp = Path(tempfile.mkdtemp(prefix="conan-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["GEMINI_API_KEY"] = ""
os.environ.setdefault("LLM_MODE", "live")

import pytest  # noqa: E402

from app.db import init_db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    init_db()
    yield


@pytest.fixture(autouse=True)
def _isolated_analysis_cache():
    """Tests share one DB and often upload the same synthetic PDF: give each test its own
    PIPELINE_VERSION (part of the analysis_cache key) so cached results never leak between tests."""
    import uuid

    from app.config import get_settings
    s = get_settings()
    old = s.pipeline_version
    s.pipeline_version = f"test-{uuid.uuid4().hex[:8]}"
    yield
    s.pipeline_version = old
