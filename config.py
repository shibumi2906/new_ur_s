import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")
    
    # Proxy Configuration
    PROXY_URL = os.getenv("PROXY_URL", "http://user179631:g7340x@166.1.76.142:1196")
    
    # Default Credentials
    DEFAULT_EMAIL = os.getenv("DEFAULT_EMAIL", "kseniya.194901@gmail.com")
    DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD", "Stas_2001")
    
    # Base URL
    BASE_URL = os.getenv("BASE_URL", "https://app.conneto.com/")
    
    # Selenium Configuration
    SELENIUM_TIMEOUT = 20
    MAX_RETRIES = 3
    
    # LLM Configuration
    LLM_MODEL = "gpt-4o"
    LLM_TEMPERATURE = 0.3
    
    # Memory Configuration
    MAX_MEMORY_ITEMS = 10 