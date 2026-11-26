from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


KNOWN_INSECURE_JWT_SECRET = "bidguard-insecure-dev-secret-key-change-in-production-min-32-chars"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Project Info
    PROJECT_NAME: str = "GeM Bid Compliance Verification Platform"
    PROJECT_DESCRIPTION: str = "AI-Powered Integrated Bid Compliance Verification Platform for GeM Procurement (SIH26100)"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    # Environment & Runtime Mode
    ENVIRONMENT: str = "development"  # "development", "test", "production"
    DEBUG: bool = False

    # Server Settings
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/gem_compliance"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgrespassword@localhost:5432/gem_compliance"
    ALLOW_SQLITE_FALLBACK: bool = False
    SQLITE_FALLBACK_URL: str = "sqlite+aiosqlite:///./gem_compliance.db"

    # NVIDIA NIM / API Settings
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "openai/gpt-oss-20b"
    NVIDIA_EMBEDDING_MODEL: str = "nvidia/nemotron-3.5-embed-1b"
    EMBEDDING_DIM: int = 2048
    ALLOW_MOCK_EMBEDDINGS: bool = False

    # Evidence Retrieval
    DEFAULT_RETRIEVAL_TOP_K: int = 3

    # Uploads & Storage
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # Authentication & Security (Phase 1 Enterprise)
    JWT_SECRET_KEY: str = KNOWN_INSECURE_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ISSUER: str = "bidguard-ai"
    JWT_AUDIENCE: str = "bidguard-platform"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    AUTH_DEV_MODE: bool = False
    ALLOW_PUBLIC_ORG_SIGNUP: bool = False

    # OCR Settings (Phase 7)
    ENABLE_OCR: bool = True
    OCR_ENGINE: str = "paddle"  # "paddle" or "mock"
    OCR_LANGUAGE: str = "en"  # Default deployment language: English
    OCR_CONFIDENCE_THRESHOLD: float = 0.75

    def validate_production_security(self) -> None:
        """Fail fast at startup if insecure defaults are active in production."""
        if self.ENVIRONMENT.lower() != "production":
            return

        errors: List[str] = []
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == KNOWN_INSECURE_JWT_SECRET or len(self.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY must be a strong, non-default secret of at least 32 characters in production.")
        if self.AUTH_DEV_MODE:
            errors.append("AUTH_DEV_MODE must be False in production.")
        if self.ALLOW_MOCK_EMBEDDINGS:
            errors.append("ALLOW_MOCK_EMBEDDINGS must be False in production.")
        if self.DEBUG:
            errors.append("DEBUG must be False in production.")
        if not self.COOKIE_SECURE:
            errors.append("COOKIE_SECURE must be True in production.")
        if self.ALLOW_SQLITE_FALLBACK:
            errors.append("ALLOW_SQLITE_FALLBACK must be False in production.")
        if "*" in self.BACKEND_CORS_ORIGINS:
            errors.append("Wildcard '*' in BACKEND_CORS_ORIGINS is forbidden with credentials in production.")

        if errors:
            raise RuntimeError("Production security configuration check failed: " + " | ".join(errors))


settings = Settings()
