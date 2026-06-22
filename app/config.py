import os

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ENV = os.getenv("APP_ENV", "local")


class Settings(BaseSettings):

    DEBUG: bool = False
    COOKIE_SECURE: bool | None = None
    COOKIE_SAMESITE: str | None = None
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cookie_secure(self) -> bool:
        return (not self.DEBUG) if self.COOKIE_SECURE is None else self.COOKIE_SECURE

    @property
    def cookie_samesite(self) -> str:
        if self.COOKIE_SAMESITE is not None:
            return self.COOKIE_SAMESITE
        return "lax" if self.DEBUG else "none"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

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

    # FERNET ENCRYPTION KEY
    KYC_ENCRYPTION_KEY: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 90
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    SESSION_REFRESH_TOKEN_EXPIRE_HOURS: int = 24

    # RAPID API
    RAPIDAPI_KEY: str
    RAPIDAPI_HOST: str

    # RAPID API — live train running status (provider: train-running-api)
    RAPIDAPI_LIVE_STATUS_KEY: str = ""
    RAPIDAPI_LIVE_STATUS_HOST: str = "train-running-api.p.rapidapi.com"
    RAPIDAPI_LIVE_STATUS_BASE_URL: str = "https://train-running-api.p.rapidapi.com"
    RAPIDAPI_LIVE_STATUS_TIMEOUT_SECONDS: int = 15

    # AUTOFILL (Smart Form Autofill — Level 1 rules)
    AI_CONFIDENCE_THRESHOLD: float = (
        0.75  # >= this -> auto-fill; below -> suggestion only
    )

    # GEMINI API
    GEMINI_API_KEY: str
    GEMINI_API_KEY_NAME: str
    GEMINI_API_PROJECT_NAME: str
    GEMINI_API_PROJECT_NUMBER: str
    GEMINI_TEMPERATURE: float = 0.2
    GEMINI_MAX_OUTPUT_TOKENS: int = 2048

    # SUPABASE
    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_TICKET_BUCKET: str
    SUPABASE_IMAGE_BUCKET: str

    # PAYMENT
    PAYMENT_MODE: str = "mock"
    MOCK_VALID_CREDIT_CARD: str
    MOCK_VALID_DEBIT_CARD: str
    MOCK_VALID_UPI_ID: str
    MOCK_VALID_NETBANKING_USER: str
    MOCK_VALID_NETBANKING_PASS: str
    MOCK_VALID_CVV: str = "123"

    # GOOGLE AUTH
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_PROVIDER: str = "google"

    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{APP_ENV}"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
