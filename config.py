from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    TOKEN: str
    MONGO_URI: str
    MONGODB_DB: str = "polski"
    
    # Ключи для ИИ
    GEMINI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    
    CHANNEL_ID: str
    
    # Webhook settings
    WEBHOOK_HOST: str = "localhost"
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_PORT: int = 10000
    IS_PRODUCTION: bool = False
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
