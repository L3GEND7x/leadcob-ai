from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "LeadCob AI"
    app_env: str = "development"
    database_url: str = "sqlite:///./leadcob.db"
    db_host: str = ""
    postgres_password: str = ""
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "development-only"
    admin_username: str = "admin"
    admin_password_hash: str = ""
    public_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    assistant_monthly_budget_usd: float = 0
    openai_input_usd_per_million: float = 0
    openai_output_usd_per_million: float = 0
    brave_search_api_key: str = ""
    # exemplos fictícios só quando pedidos explicitamente (nunca em uso real)
    demo_seed: bool = False
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
