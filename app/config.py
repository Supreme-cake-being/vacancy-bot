from pydantic_settings import BaseSettings
from pydantic import PostgresDsn

class Settings(BaseSettings):
    # Telegram
    BOT_TOKEN: str
    ADMIN_TG_ID: int | None = None

    # Database
    DATABASE_URL: str       # asyncpg — for SQLAlchemy async
    DATABASE_URL_SYNC: str  # psycopg2 — for Alembic

    # Task Queue
    REDIS_URL: str = "redis://localhost:6379/0"

    # Parser Behavior
    CHECK_INTERVAL_MINUTES: int = 60      # how often to check websites
    REQUEST_DELAY_MIN: float = 2.0        # minimum delay between requests
    REQUEST_DELAY_MAX: float = 6.0        # maximum delay between requests
    MAX_RETRIES: int = 3                  # number of retry attempts

    # Environment
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Single global instance — import from here throughout the app
settings = Settings()