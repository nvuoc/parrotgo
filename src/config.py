"""Application configuration settings using pydantic-settings."""

from pathlib import Path
from typing import Literal, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Session defaults
    DEFAULT_SESSION_CITY: Optional[str] = Field(default=None)
    SESSION_TIMEZONE: str = Field(default="Asia/Ho_Chi_Minh")

    # Map settings
    MAP_MODE: Literal["mock", "live"] = Field(default="mock")  # "mock" | "live"
    VIETMAP_API_KEY: Optional[str] = Field(default=None)
    MAP_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    GEO_DATA_PATH: str = Field(default="data/snapshot_places.json")

    # LLM settings
    LLM_MODE: Literal["mock", "gemini", "groq"] = Field(default="mock")  # "mock" | "gemini" | "groq"
    GEMINI_API_KEY: Optional[str] = Field(default=None)
    GEMINI_MODEL: str = Field(default="gemini-3.5-flash-lite")
    GROQ_API_KEY: Optional[str] = Field(default=None)
    GROQ_MODEL: str = Field(default="openai/gpt-oss-120b")
    LLM_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0, le=120)
    LLM_MAX_RETRIES: int = Field(default=0, ge=0, le=2)

    # Passenger limits for the demo fleet; adjust for the actual fleet.
    MAX_PASSENGERS_XE_MAY: int = Field(default=1, ge=1)
    MAX_PASSENGERS_OTO_4_CHO: int = Field(default=4, ge=1)
    MAX_PASSENGERS_OTO_7_CHO: int = Field(default=7, ge=1)

    # RAG / Embedding settings
    RAG_ENABLED: bool = Field(default=False)
    EMBEDDING_PROVIDER: Optional[str] = Field(default="onnx")
    EMBEDDING_MODEL: Optional[str] = Field(default="all-MiniLM-L6-v2")
    EMBEDDING_DIMENSIONS: Optional[int] = Field(default=384)

    # Storage paths
    PERSISTENT_DB_PATH: str = Field(default="data/parrotgo.db")
    CHROMA_DATA_DIR: str = Field(default="data/chroma_data")

    # Debug mode
    DEBUG: bool = Field(default=False)

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_mode(cls, value):
        # Some launchers export DEBUG=release/debug rather than a boolean.
        if isinstance(value, str) and value.lower() in {"release", "debug"}:
            return value.lower() == "debug"
        return value

    @model_validator(mode="after")
    def auto_enable_live_mode_if_keys_present(self) -> "Settings":
        # Auto-enable live Vietmap when API key is present unless explicitly set to mock in env
        if self.VIETMAP_API_KEY and self.MAP_MODE == "mock" and "MAP_MODE" not in self.model_fields_set:
            self.MAP_MODE = "live"
        # Auto-enable live LLM (Gemini or Groq) when API key is present unless explicitly set to mock in env
        if self.LLM_MODE == "mock" and "LLM_MODE" not in self.model_fields_set:
            if self.GEMINI_API_KEY:
                self.LLM_MODE = "gemini"
            elif self.GROQ_API_KEY:
                self.LLM_MODE = "groq"
        return self

    def get_db_path(self, base_dir: Optional[Path] = None) -> Path:
        p = Path(self.PERSISTENT_DB_PATH)
        if p.is_absolute():
            return p
        base = base_dir or Path.cwd()
        return (base / p).resolve()

    def get_chroma_dir(self, base_dir: Optional[Path] = None) -> Path:
        p = Path(self.CHROMA_DATA_DIR)
        if p.is_absolute():
            return p
        base = base_dir or Path.cwd()
        return (base / p).resolve()


settings = Settings()
