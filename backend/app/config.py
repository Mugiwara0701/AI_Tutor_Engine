"""
Centralized application configuration.

Loads and validates environment variables using pydantic-settings.
Import `settings` anywhere in the app instead of reading os.environ directly.

NOTE: This backend does NOT use Supabase Auth or the Supabase client library.
Authentication is fully self-managed: passwords are hashed and stored in our
own Postgres table, and JWTs are minted/verified by this backend using
JWT_SECRET. The only Supabase-provided piece we depend on is the direct
Postgres connection string (DATABASE_URL).
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ---- Database (direct Postgres connection string from Supabase) ----
    DATABASE_URL: str = Field(..., description="Direct Postgres connection string")

    # ---- JWT / Auth (self-managed, not Supabase Auth) ----
    JWT_SECRET: str = Field(..., description="Secret used to sign and verify our own JWTs")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)

    # ---- App / CORS ----
    FRONTEND_URL: str = Field(default="http://localhost:5173")
    BACKEND_HOST: str = Field(default="127.0.0.1")
    BACKEND_PORT: int = Field(default=8000)

    # ---- Behavior flags ----
    AUTO_CREATE_TABLES: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="development")

    @field_validator("DATABASE_URL", "JWT_SECRET")
    @classmethod
    def not_empty(cls, v: Optional[str], info):
        if v is None or str(v).strip() == "":
            raise ValueError(
                f"Missing required environment variable: {info.field_name}. "
                f"Copy Backend/.env.example to Backend/.env and fill in the values."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings loader. Raises a clear, readable error on startup
    if required environment variables are missing or invalid, instead
    of failing deep inside request handling.
    """
    try:
        return Settings()
    except Exception as exc:  # pydantic ValidationError
        raise RuntimeError(
            "Invalid or missing environment configuration.\n"
            f"Details: {exc}\n\n"
            "Fix: copy Backend/.env.example to Backend/.env and fill in all values."
        ) from exc


settings = get_settings()
