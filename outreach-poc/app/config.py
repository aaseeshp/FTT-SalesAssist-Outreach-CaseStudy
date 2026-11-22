"""Runtime settings, read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (project folder first, then its parent). Real env vars win."""
    for env_file in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        if env_file.exists():
            _read_env(env_file)


def _read_env(env_file: Path) -> None:
    for raw in env_file.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    llm_provider: str  # "auto" | "claude" | "gemini" | "template"
    claude_model: str
    claude_fallback_models: list[str]
    llm_timeout_s: float
    gemini_api_key: str | None
    gemini_model: str
    gemini_fallback_models: list[str]
    gemini_timeout_ms: int
    drafter: str  # "auto" | "gemini" | "template"
    warm_cache: bool


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("DATA_DIR", str(BASE_DIR / "data"))),
        llm_provider=os.getenv("LLM_PROVIDER", "auto").lower(),
        claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        claude_fallback_models=[m.strip() for m in os.getenv(
            "CLAUDE_FALLBACK_MODELS", "claude-haiku-5-5").split(",") if m.strip()],
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", "60")),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-4-hydrogen"),
        gemini_fallback_models=[m.strip() for m in os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash,gemini-3.5-flash-lite").split(",") if m.strip()],
        gemini_timeout_ms=int(os.getenv("GEMINI_TIMEOUT_MS", "45000")),
        drafter=os.getenv("DRAFTER", "auto").lower(),
        warm_cache=os.getenv("WARM_CACHE", "true").lower() == "true",
    )
