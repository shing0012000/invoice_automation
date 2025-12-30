import os
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Union

class Settings(BaseSettings):
    """
    Application settings with explicit validation and safe defaults.
    All environment variables are parsed explicitly with clear error messages.
    """
    # Database URL - supports PostgreSQL or SQLite
    # SQLite format: sqlite:///./invoice_demo.db
    # PostgreSQL format: postgresql+psycopg://user:pass@host:5432/dbname
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/invoices",
        description="Database connection URL (PostgreSQL or SQLite)"
    )
    
    storage_dir: str = Field(
        default="./storage",
        description="Directory for storing uploaded invoice files"
    )
    
    max_attempts: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum retry attempts for processing"
    )
    
    # Demo mode flag - explicit boolean parsing
    demo_mode: bool = Field(
        default=False,
        description="Enable demo mode (hides Swagger, exposes only demo endpoints)"
    )
    
    # Server port - explicit integer parsing
    port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Server port (cloud platforms set PORT automatically)"
    )

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v or not v.strip():
            raise ValueError("DATABASE_URL cannot be empty")
        v = v.strip()
        # Check for supported database types
        if not (v.startswith("sqlite:///") or 
                v.startswith("postgresql://") or 
                v.startswith("postgresql+psycopg://")):
            raise ValueError(
                f"Unsupported database URL format: {v}. "
                "Supported formats: sqlite:///..., postgresql://..., postgresql+psycopg://..."
            )
        return v
    
    @field_validator('demo_mode', mode='before')
    @classmethod
    def parse_demo_mode(cls, v: Union[str, bool]) -> bool:
        """Parse demo mode from string or boolean."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            v_lower = v.lower().strip()
            if v_lower in ('true', '1', 'yes', 'on'):
                return True
            elif v_lower in ('false', '0', 'no', 'off', ''):
                return False
            else:
                raise ValueError(
                    f"Invalid DEMO_MODE value: '{v}'. "
                    "Must be one of: true, false, 1, 0, yes, no, on, off"
                )
        return False
    
    @field_validator('port', 'max_attempts', mode='before')
    @classmethod
    def parse_int(cls, v: Union[str, int]) -> int:
        """Parse integer from string or int."""
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            try:
                return int(v.strip())
            except ValueError:
                raise ValueError(f"Invalid integer value: '{v}'")
        raise ValueError(f"Cannot parse integer from: {type(v)}")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Create settings instance - will raise ValidationError if invalid
try:
    settings = Settings()
except Exception as e:
    import sys
    print(f"ERROR: Configuration validation failed: {e}", file=sys.stderr)
    print("Please check your environment variables and .env file.", file=sys.stderr)
    sys.exit(1)

