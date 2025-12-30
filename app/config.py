import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database URL - supports PostgreSQL or SQLite
    # SQLite format: sqlite:///./invoice_demo.db
    # PostgreSQL format: postgresql+psycopg://user:pass@host:5432/dbname
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/invoices"
    )
    storage_dir: str = os.getenv("STORAGE_DIR", "./storage")
    max_attempts: int = int(os.getenv("MAX_ATTEMPTS", "5"))
    
    # Demo mode flag
    demo_mode: bool = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    # Server port (for Render deployment)
    port: int = int(os.getenv("PORT", "8000"))

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

