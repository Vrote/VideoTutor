import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application Settings loaded from environment variables or .env file."""

    APP_NAME: str = "VideoTutor - AI Video Learning Agent"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = "development"

    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    HUGGINGFACE_API_KEY: str = ""
    
    LLM_MODEL: str = "gemini-1.5-flash"
    GROQ_MODEL: str = "compound-beta-mini"
    
    EMBEDDING_PROVIDER: str = "default"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    CHROMA_PERSIST_DIRECTORY: str = "../chroma_data"

    
    SEARCH_RELEVANCE_THRESHOLD: float = 1.65

    model_config = SettingsConfigDict(
        env_file=(
            os.path.join(os.path.dirname(__file__), "..", ".env"),
            ".env",
            "backend/.env"
        ),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
