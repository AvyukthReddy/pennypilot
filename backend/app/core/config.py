from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://pennypilot:pennypilot@localhost:5432/pennypilot"
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
