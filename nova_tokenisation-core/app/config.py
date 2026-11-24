from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str
    REDIS_URL: str
    ENVIRONMENT: str = "development"
    JWT_SECRET: str = "change_me"
    KYC_PROVIDER: str = "mock"
    AML_PROVIDER: str = "mock"

settings = Settings()
