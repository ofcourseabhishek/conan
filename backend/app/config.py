"""Environment settings (TRD §15). Every knob the council plan names lives here."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local dev falls back to SQLite so the app boots without Neon; Render must set a Postgres URL.
    database_url: str = "sqlite:///./conan.db"

    gemini_api_key: str | None = None
    gemini_api_keys: str | None = None  # comma-separated extra keys, used together with gemini_api_key
    gemini_model: str = "gemini-2.5-flash"  # confirm at H0 against the quota page
    gemini_rpm: int = 10
    gemini_concurrency: int = 2
    gemini_timeout_s: float = 45.0
    batch_chars: int = 8000

    pipeline_version: str = "v1"
    prompt_version: str = "p1"
    llm_mode: Literal["live", "replay"] = "live"
    llm_record: bool = False  # live mode: also write responses to fixtures/llm/ for replay tests

    enable_p2_llm: bool = True
    enable_llm_conflicts: bool = False
    enable_reminders: bool = False

    demo_as_of: str | None = None
    resend_api_key: str | None = None
    allowed_origins: str = "http://localhost:5173"
    demo_passcode: str | None = None

    # Upload caps (TRD §5.1)
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pages: int = 30
    parse_timeout_s: float = 20.0

    @field_validator("database_url")
    @classmethod
    def _normalize_pg_scheme(cls, v: str) -> str:
        # Neon hands out postgres:// or postgresql://; SQLAlchemy needs the psycopg3 driver named.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def api_keys(self) -> list[str]:
        """All configured Gemini keys, de-duplicated, GEMINI_API_KEY first."""
        raw = [self.gemini_api_key or ""] + (self.gemini_api_keys or "").split(",")
        return list(dict.fromkeys(k.strip() for k in raw if k and k.strip()))

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
