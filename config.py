from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vapi_api_key: str
    anthropic_api_key: str
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    database_path: str = "settly.db"
    settly_api_url: str = "https://settly.up.railway.app"

    model_config = {"env_file": ".env"}


settings = Settings()
