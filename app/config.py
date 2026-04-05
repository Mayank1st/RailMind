from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # DEBUG
    DEBUG: str = False

    # DATABASE
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_SCHEMA: str
    DB_POOL_SIZE: int
    DB_MAX_OVERFLOW: int

    # LOGGING
    ECHO: bool = False

    # DEV AUTH BYPASS
    DEV_AUTH_BYPASS: bool = False

    # ENVIRONMENT
    ENVIRONMENT: str = "dev"

    # BASE API URL
    API_BASE_URL: str = "http://localhost:8000"

    # FRONTEND BASE URL
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # SMTP CONFIGURATION
    EMAIL_SMTP_USER: str
    EMAIL_SMTP_PASSWORD: str
    MAIL_FROM: str = "noreply@railmind.in"
    MAIL_PORT: str = 587
    EMAIL_SMTP_HOST: str
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # REDIS / CELERY
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # HMAC SECRET KEY
    HMAC_SECRET_KEY: str = "KYC_HMAC_SECRET"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # RAPID API
    RAPIDAPI_KEY: str
    RAPIDAPI_HOST: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
