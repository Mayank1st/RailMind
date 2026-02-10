from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

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

    # JWT
    JWT_SECRET: str
    JWT_ALGO: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # SMTP
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_FROM_NAME: str
    MAIL_STARTTLS: bool
    MAIL_SSL_TLS: bool
    USE_CREDENTIALS: bool
    VALIDATE_CERTS: bool

    # REDIS
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # GEMINI API
    GOOGLE_API_KEY: str = "AIzaSyDKd-T8ypQNy6TL83-FcJwdndJnR45ZKLE"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
