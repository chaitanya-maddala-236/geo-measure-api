"""Environment-backed application settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration with safe defaults for local development."""

    database_url: str = "sqlite:///./geo_measure.db"
    max_upload_size_bytes: int = 50 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 200 * 1024 * 1024
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
