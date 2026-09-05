from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./remedygraph.db"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = "whsec_test"
    razorpay_mode: str = "fake"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    claim_compiler_mode: str = "heuristic"
    incident_linker_mode: str = "heuristic"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"


settings = Settings()
