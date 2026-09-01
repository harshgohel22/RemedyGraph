from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./remedygraph.db"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = "whsec_test"
    razorpay_mode: str = "fake"
    claim_compiler_mode: str = "heuristic"


settings = Settings()
