from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LeadCob AI"
    app_env: str = "development"
    database_url: str = "sqlite:///./leadcob.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "development-only"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
