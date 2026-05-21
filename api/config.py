import os
from typing import Optional


class Settings:
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # Vendrix (WhatsApp)
    VENDRIX_API_KEY: str = os.getenv("VENDRIX_API_KEY", "")
    VENDRIX_API_URL: str = os.getenv("VENDRIX_API_URL", "https://api.vendrix.net")
    VENDRIX_WEBHOOK_SECRET: str = os.getenv("VENDRIX_WEBHOOK_SECRET", "")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")

    # Notifications
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    NOTIFICATION_EMAIL_FROM: str = os.getenv("NOTIFICATION_EMAIL_FROM", "")

    # Bot behavior
    BOT_ENABLED: bool = os.getenv("BOT_ENABLED", "true").lower() == "true"
    SESSION_TIMEOUT_MINUTES: int = 60


settings = Settings()
