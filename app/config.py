"""Application configuration. All secrets come from environment variables."""
import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

_DEV_SECRET_MARKER = "change-me"


def _database_url(name="DATABASE_URL", default=None):
    url = os.getenv(name, default)
    if url:
        # Some hosts still hand out the legacy "postgres://" scheme.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # Pin the driver we install (psycopg2). Newer SQLAlchemy versions would
        # otherwise default a bare "postgresql://" URL to psycopg3.
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _csv(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class BaseConfig:
    APP_ENV = "development"
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.getenv("SECRET_KEY", f"dev-secret-{_DEV_SECRET_MARKER}")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", f"dev-jwt-secret-{_DEV_SECRET_MARKER}")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60")))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7")))

    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Comma separated list of allowed browser origins (your React app).
    CORS_ORIGINS = _csv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")

    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "twende-majuu")

    # Upload limits.
    MAX_IMAGE_SIZE_MB = int(os.getenv("MAX_IMAGE_SIZE_MB", "5"))
    MAX_DOCUMENT_SIZE_MB = int(os.getenv("MAX_DOCUMENT_SIZE_MB", "10"))
    MAX_DOCUMENTS_PER_APPLICANT = int(os.getenv("MAX_DOCUMENTS_PER_APPLICANT", "25"))
    # Hard cap on any request body (largest file + form overhead).
    MAX_CONTENT_LENGTH = (MAX_DOCUMENT_SIZE_MB + 2) * 1024 * 1024

    # Signed download links to Cloudinary are only ever used server-side and
    # expire after this many seconds.
    DOWNLOAD_URL_TTL_SECONDS = int(os.getenv("DOWNLOAD_URL_TTL_SECONDS", "120"))

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    APP_ENV = "development"
    DEBUG = True


class TestingConfig(BaseConfig):
    APP_ENV = "testing"
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret-that-is-long-enough-for-hs256"
    # In-memory SQLite by default; set TEST_DATABASE_URL to run against PostgreSQL.
    SQLALCHEMY_DATABASE_URI = _database_url("TEST_DATABASE_URL", "sqlite:///:memory:")
    CLOUDINARY_CLOUD_NAME = "test"
    CLOUDINARY_API_KEY = "test"
    CLOUDINARY_API_SECRET = "test"
    CORS_ORIGINS = ["http://localhost:5173"]


class ProductionConfig(BaseConfig):
    APP_ENV = "production"


_CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name=None):
    name = (name or os.getenv("APP_ENV") or "development").lower()
    try:
        return _CONFIGS[name]
    except KeyError:
        raise RuntimeError(f"Unknown APP_ENV '{name}'. Use one of: {', '.join(_CONFIGS)}.")


def validate_config(config):
    """Fail fast on unsafe or incomplete configuration."""
    if not config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and fill it in.")
    if config["APP_ENV"] == "production":
        for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
            value = config.get(key) or ""
            if _DEV_SECRET_MARKER in value or len(value) < 32:
                raise RuntimeError(f"{key} must be set to a random value of at least 32 characters in production.")
