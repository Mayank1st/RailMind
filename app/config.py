from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


settings = Settings()
