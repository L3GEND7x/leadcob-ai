from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LeadCob AI"
    app_env: str = "development"
    database_url: str = "sqlite:///./leadcob.db"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "development-only"
    # exemplos fictícios só quando pedidos explicitamente (nunca em uso real)
    demo_seed: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
