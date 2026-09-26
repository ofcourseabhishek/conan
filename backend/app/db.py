from collections.abc import Iterator

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False})

            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # SQLite ignores ON DELETE CASCADE unless asked
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
        else:
            # Neon autosuspends: pre-ping drops dead connections; small pool for Render's 512 MB.
            _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, pool_recycle=300)
    return _engine


def init_db() -> None:
    import app.models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def ping() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
