# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, computed_field


class Settings(BaseSettings):
    """
    Configuration for the Onboarding KOF backend.
    Loads environment variables from .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_case=True, extra="ignore"
    )

    # --- Database ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_SERVER: str
    POSTGRES_DB: str
    POSTGRES_PORT: int = 5432

    # --- JWT Settings ---
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Smartsheet Configuration ---
    SMARTSHEET_ACCESS_TOKEN: str
    SMARTSHEET_API_BASE_URL: str = "https://api.smartsheet.com/2.0"
    MIDDLEWARE_API_KEY: str
    SHEET_ID: int = 7060277951418244

    # --- Google Cloud Storage Settings ---
    GCS_BUCKET_NAME: str = "entersys-onboarding-photos"
    GCS_PROJECT_ID: str = "mi-infraestructura-web"

    # --- Email/SMTP Settings (Gmail) ---
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@entersys.mx"
    SMTP_FROM_NAME: str = "Entersys"
    FRONTEND_URL: str = "https://www.entersys.mx"

    # --- Smartsheet Webhook ---
    SMARTSHEET_WEBHOOK_CALLBACK_URL: str = ""

    @computed_field
    @property
    def DATABASE_URI(self) -> str:
        dsn = PostgresDsn.build(
            scheme="postgresql+psycopg2",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )
        return str(dsn)


settings = Settings()
