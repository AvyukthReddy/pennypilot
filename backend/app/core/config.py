from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    environment: str = "development"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    supabase_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_publishable_key: str = Field(
        default="", validation_alias="NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"
    )
    frontend_origin: str = "http://localhost:3000"


settings = Settings()
