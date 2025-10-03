from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    aws_s3_bucket: str = Field(..., env="AWS_S3_BUCKET")

    database_url: str = Field(
        default=f"sqlite:///{Path.cwd() / 'data' / 'epubs.db'}",
        env="DATABASE_URL",
    )

    s3_presign_expiration: int = Field(default=3600, env="S3_PRESIGN_EXPIRATION")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()  # type: ignore[arg-type]
