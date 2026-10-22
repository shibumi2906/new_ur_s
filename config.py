import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Proxy Configuration
    PROXY_URL = os.getenv("PROXY_URL", "")

    # Default Credentials
    DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL", "")
    DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "")

    # Base URL
    BASE_URL = os.getenv("BASE_URL", "https://app.conneto.com/")

    # Selenium Configuration
    SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "20"))
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

    # LLM Configuration
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

    # Memory Configuration
    MAX_MEMORY_ITEMS = int(os.getenv("MAX_MEMORY_ITEMS", "10"))
