from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Storage backend configuration
    storage_backend: Literal["s3", "google_drive", "local"] = Field(
        default="local", env="STORAGE_BACKEND"
    )

    # AWS S3 configuration
    aws_access_key_id: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field(default="us-east-1", env="AWS_REGION")
    aws_s3_bucket: Optional[str] = Field(default=None, env="AWS_S3_BUCKET")
    aws_s3_endpoint_url: Optional[str] = Field(default=None, env="AWS_S3_ENDPOINT_URL")

    # Cloudflare R2 compatibility aliases (used when AWS-style keys are not provided)
    r2_access_key_id: Optional[str] = Field(default=None, env="R2_ACCESS_KEY_ID")
    r2_secret_access_key: Optional[str] = Field(default=None, env="R2_SECRET_ACCESS_KEY")
    r2_bucket: Optional[str] = Field(default=None, env="R2_BUCKET")
    r2_endpoint_url: Optional[str] = Field(default=None, env="R2_ENDPOINT_URL")
    r2_region: Optional[str] = Field(default=None, env="R2_REGION")

    # Google Drive configuration
    google_service_account_json: Optional[str] = Field(default=None, env="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_service_account_file: Optional[str] = Field(default=None, env="GOOGLE_SERVICE_ACCOUNT_FILE")
    google_drive_folder_id: Optional[str] = Field(default=None, env="GOOGLE_DRIVE_FOLDER_ID")
    google_impersonated_user: Optional[str] = Field(default=None, env="GOOGLE_IMPERSONATED_USER")

    # Database configuration
    database_url: str = Field(
        default=f"sqlite:///{Path.cwd() / 'data' / 'epubs.db'}",
        env="DATABASE_URL",
    )

    # Local storage configuration
    local_storage_path: str = Field(default="books", env="LOCAL_STORAGE_PATH")

    s3_presign_expiration: int = Field(default=3600, env="S3_PRESIGN_EXPIRATION")

    @property
    def resolved_s3_access_key_id(self) -> Optional[str]:
        return self.aws_access_key_id or self.r2_access_key_id

    @property
    def resolved_s3_secret_access_key(self) -> Optional[str]:
        return self.aws_secret_access_key or self.r2_secret_access_key

    @property
    def resolved_s3_bucket(self) -> Optional[str]:
        return self.aws_s3_bucket or self.r2_bucket

    @property
    def resolved_s3_endpoint_url(self) -> Optional[str]:
        return self.aws_s3_endpoint_url or self.r2_endpoint_url

    @property
    def resolved_s3_region(self) -> str:
        return self.r2_region or self.aws_region

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()  # type: ignore[arg-type]


# Create a global settings instance for convenience
settings = get_settings()
