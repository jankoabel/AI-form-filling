"""Settings from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_dir: Path
    llm_provider: str  # "openrouter" | "mock"
    llm_api_key: str | None
    llm_model: str
    llm_base_url: str
    llm_timeout: float
    max_upload_mb: int

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", "./data")).resolve()
        key = os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY") or None
        provider = os.getenv("LLM_PROVIDER") or ("openrouter" if key else "mock")
        return cls(
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{data_dir / 'formfill.db'}"),
            data_dir=data_dir,
            llm_provider=provider.lower(),
            llm_api_key=key,
            llm_model=os.getenv("LLM_MODEL", "google/gemma-4-31b-it:free"),
            llm_base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            llm_timeout=float(os.getenv("LLM_TIMEOUT", "90")),
            max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "10")),
        )
