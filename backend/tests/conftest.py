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
