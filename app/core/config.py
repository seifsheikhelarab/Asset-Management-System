from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://app:app@localhost:5432/assets"
    auth_api_key: str = "change-me"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    default_org_id: str = "default"
    llm_api_key: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "gpt-4o-mini"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
