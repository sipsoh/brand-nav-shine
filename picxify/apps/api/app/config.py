from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_NAME = "picxify-api"
SERVICE_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"

    database_url: str = "postgresql+psycopg://picxify:picxify@localhost:5432/picxify"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_bucket: str = "picxify-dev"
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True

    clerk_secret_key: str = ""
    clerk_jwks_url: str = ""

    max_upload_mb_free: int = 10
    max_upload_mb_creator: int = 100

    @property
    def cors_origins(self) -> list[str]:
        return [self.app_url]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
