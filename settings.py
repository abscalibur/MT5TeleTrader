from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file if it exists

class Settings(BaseSettings):
    # telegram_setting
    TELEGRAM_API_ID: int = os.environ.get('TELEGRAM_API_ID',0)
    TELEGRAM_API_HASH: str = os.environ.get("TELEGRAM_API_HASH",'')
    TELEGRAM_SESSION_NAME: str = "runtime/mainsession"
    PHONE_NUMBER: str = os.environ.get("PHONE_NUMBER","")

    # database_setting
    DATABASE_URL: str = "sqlite:///runtime/metaauto.db"

    # ops settings
    CHANNEL_SYNC_INTERVAL_MINUTES: int = 60
    MESSAGE_SYNC_INTERVAL_MINUTES: int = 1
    MESSAGE_SYNC_LOOKBACK_MINUTES: int = 3
    MESSAGE_SYNC_LIMIT_PER_CHANNEL: int = 100
    TRADE_EXECUTION_INTERVAL_MINUTES: int = 1

    # AI trade interpretation settings
    TRADE_INTERPRETATION_INTERVAL_MINUTES: int = 1
    NVIDIA_API_KEY: str = os.environ.get("NVIDIA_API_KEY","")
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_MODEL: str = "openai/gpt-oss-120b"
    NVIDIA_REASONING_EFFORT: str = "high"
    NVIDIA_TEMPERATURE: float = 0
    NVIDIA_MAX_TOKENS: int = 500
    NVIDIA_PARSE_RETRIES: int = 1
    NVIDIA_PARSE_TIMEOUT_SECONDS: float = 60

    # MetaApi trade execution settings
    METAAPI_TOKEN: str = os.environ.get("METAAPI_TOKEN","")
    METAAPI_ACCOUNT_ID: str = os.environ.get("METAAPI_ACCOUNT_ID","")
    TRADE_VOLUME: float = 0.01

    # logging settings
    LOG_LEVEL: str = "INFO"


settings = Settings()
if not all([settings.TELEGRAM_API_HASH,
            settings.TELEGRAM_API_ID,
            settings.PHONE_NUMBER,
            settings.NVIDIA_API_KEY,
            settings.METAAPI_TOKEN,
            settings.METAAPI_ACCOUNT_ID]):
    raise ValueError("Please set all required environment variables.")
