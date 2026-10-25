import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # App Information
    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8002
    LOG_LEVEL: str = "INFO"
    PROJECT_NAME: str = "EVCharge-Opt"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = Field(
        default="sqlite:///./evcharge_opt.db",
        description="SQLAlchemy database URL (SQLite local fallback or PostgreSQL)",
    )

    # Provider Mode ("mock" or "live")
    PREDICT_PROVIDER_MODE: str = Field(
        default="mock",
        description="Forecast provider mode: 'mock' or 'live'",
    )
    PREDICT_API_BASE_URL: str = Field(
        default="http://127.0.0.1:8001",
        description="Base URL for live EVCharge-Predict API",
    )
    PREDICT_SERVICE_TOKEN: Optional[str] = Field(
        default=None,
        description="Backend-to-backend authentication token for EVCharge-Predict",
    )
    PREDICT_TIMEOUT_SECONDS: float = Field(
        default=10.0,
        description="HTTP request timeout for live provider adapter",
    )

    # CORS
    CORS_ORIGINS: str = Field(
        default="http://127.0.0.1:5174,http://localhost:5174",
        description="Comma-separated list of allowed CORS origins",
    )

    # Optimization & Feedback Defaults
    DEFAULT_DEFERRED_FRACTION: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Portion of unserved demand assumed to defer to the next interval",
    )

    # Station Integration Profile & Physical Verification
    STATION_INTEGRATION_PROFILE: str = Field(
        default="five_station_mock",
        description="Active station profile: 'five_station_mock' (all 5 local stations) or 'three_station_integration' (initial 3-station predictor profile)",
    )
    CONFIRM_PHYSICAL_STATION_MAPPINGS: bool = Field(
        default=False,
        description="Explicit confirmation flag for physical correspondence of proposed candidate station mappings (STN-01..03 -> ST-001..003)",
    )
    PREDICT_SUPPORTED_STATIONS: str = Field(
        default="ST-001,ST-002,ST-003",
        description="Comma-separated list of canonical station identifiers supported by the EVCharge-Predict model",
    )

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def predict_supported_stations_list(self) -> List[str]:
        return [stn.strip() for stn in self.PREDICT_SUPPORTED_STATIONS.split(",") if stn.strip()]

    @property
    def is_mock_provider(self) -> bool:
        return self.PREDICT_PROVIDER_MODE.strip().lower() == "mock"

    def get_database_url(self) -> str:
        """Returns normalized database URL. Anchors relative SQLite paths to the project root."""
        url = self.DATABASE_URL
        if url.startswith("sqlite:///./") or url == "sqlite:///evcharge_opt.db":
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            db_name = url.split("/")[-1]
            abs_db_path = project_root / db_name
            return f"sqlite:///{abs_db_path.as_posix()}"
        return url

    def get_safe_predict_url(self) -> str:
        """Returns the configured predict API URL without any sensitive embedded credentials."""
        if not self.PREDICT_API_BASE_URL:
            return ""
        # Redact any basic auth credentials if present in URL
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self.PREDICT_API_BASE_URL)
            if parsed.password or parsed.username:
                hostname = parsed.hostname or ""
                port = f":{parsed.port}" if parsed.port else ""
                netloc = f"***:***@{hostname}{port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return self.PREDICT_API_BASE_URL
        except Exception:
            return "http://***"


settings = Settings()
