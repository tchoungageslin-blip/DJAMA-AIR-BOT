import os
from typing import Optional


class Settings:
    # LLM (OpenRouter)
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-4o")

    # Audio Transcription (Groq is recommended for fast/free Whisper)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # WhatsApp (Cloud API or Vendrix)
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("EXPO_PUBLIC_WHATSAPP_PHONE_ID", os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""))
    WHATSAPP_TOKEN: str = os.getenv("EXPO_PUBLIC_WHATSAPP_TOKEN", "")
    VENDRIX_API_KEY: str = os.getenv("VENDRIX_API_KEY", "")
    VENDRIX_API_URL: str = os.getenv("VENDRIX_API_URL", "https://api.vendrix.net")
    VENDRIX_WEBHOOK_SECRET: str = os.getenv("VENDRIX_WEBHOOK_SECRET", "djama-secret-123")

    # Meta WhatsApp Cloud API webhook verification token
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", os.getenv("VENDRIX_WEBHOOK_SECRET", "djama-secret-123"))

    # Auth
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24

    # App
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_URL: str = os.getenv("APP_URL", "http://localhost:3000")

    # Notifications (Resend)
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_FROM_EMAIL: str = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    NOTIFICATION_EMAIL_TO: str = os.getenv("NOTIFICATION_EMAIL_TO", "airdjama@gmail.com")

    # Bot behavior
    BOT_ENABLED: bool = os.getenv("BOT_ENABLED", "true").lower() == "true"
    SESSION_TIMEOUT_MINUTES: int = 60


settings = Settings()
