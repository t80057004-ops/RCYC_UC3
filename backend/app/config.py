"""Environment-driven configuration and logging setup for MARIS RCYC Concierge."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "infa.env", override=True)


@dataclass(frozen=True)
class Settings:
    """Application runtime configuration loaded from server environment variables."""

    port: int
    log_level: str
    sample_data_json: Path
    data_provider_mode: str
    demo_mode: bool
    llm_provider: str
    gemini_api_key: str
    gemini_model: str
    ollama_base_url: str
    ollama_model: str
    anthropic_api_key: str
    anthropic_model: str
    infa_login_url: str = ""
    infa_username: str = ""
    infa_password: str = ""
    infa_entity: str = "guest360"
    infa_guest_id_field: str = ""
    infa_customer_id_field: str = "rcyc_id"
    infa_model_version: str = ""
    infa_timeout_seconds: float = 10.0
    infa_cache_seconds: float = 60.0
    infa_max_bookings: int = 10
    infa_field_loyalty_tier: str = ""
    infa_field_preferred_regions: str = ""
    infa_field_preferred_suite: str = ""
    infa_field_interest_focus: str = ""
    infa_field_consent: str = ""
    infa_field_vip: str = ""
    infa_field_open_complaint: str = ""
    demo_assume_personalization_consent: bool = False
    secret_key: str = ""
    demo_password: str = ""
    allowed_origins: tuple[str, ...] = ()
    chat_db_path: Path = BASE_DIR / "data" / "chat.db"
    chat_retention_days: int = 30

    @classmethod
    def from_env(cls) -> "Settings":
        def resolve_path(env_key: str, default_rel: str) -> Path:
            raw = os.getenv(env_key, default_rel).strip()
            p = Path(raw)
            return p if p.is_absolute() else (BASE_DIR / p)

        def parse_bool(raw: str, default: bool) -> bool:
            val = raw.strip().lower()
            if not val:
                return default
            return val in {"1", "true", "yes", "on"}

        def parse_float(env_key: str, default: float) -> float:
            try:
                return max(float(os.getenv(env_key, str(default)).strip() or default), 0.0)
            except ValueError:
                return default

        def parse_int(env_key: str, default: int) -> int:
            try:
                return max(int(os.getenv(env_key, str(default)).strip() or default), 1)
            except ValueError:
                return default

        data_provider_mode = os.getenv("DATA_PROVIDER_MODE", "mock").strip().lower()
        raw_demo_mode = parse_bool(os.getenv("DEMO_MODE", "true"), True)
        demo_mode = False if data_provider_mode == "informatica" else raw_demo_mode

        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        # Default to gemini when GEMINI_API_KEY is present in server env (silent fallback to rule_based on failure)
        default_llm = "gemini" if gemini_key else "rule_based"

        raw_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
        allowed_origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip()) if raw_origins else ()

        return cls(
            port=parse_int("PORT", 8000),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            sample_data_json=resolve_path("SAMPLE_DATA_JSON", "data/sample_data.json"),
            data_provider_mode=data_provider_mode,
            demo_mode=demo_mode,
            llm_provider=os.getenv("LLM_PROVIDER", default_llm).strip().lower(),
            gemini_api_key=gemini_key,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip(),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip().rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip(),
            infa_login_url=os.getenv("INFA_LOGIN_URL", "").strip(),
            infa_username=os.getenv("INFA_USERNAME", "").strip(),
            infa_password=os.getenv("INFA_PASSWORD", ""),
            infa_entity=os.getenv("INFA_ENTITY", "guest360").strip() or "guest360",
            infa_guest_id_field=os.getenv("INFA_GUEST_ID_FIELD", "").strip(),
            infa_customer_id_field=os.getenv("INFA_CUSTOMER_ID_FIELD", "rcyc_id").strip() or "rcyc_id",
            infa_model_version=os.getenv("INFA_MODEL_VERSION", "").strip(),
            infa_timeout_seconds=parse_float("INFA_TIMEOUT_SECONDS", 10.0),
            infa_cache_seconds=parse_float("INFA_CACHE_SECONDS", 60.0),
            infa_max_bookings=parse_int("INFA_MAX_BOOKINGS", 10),
            infa_field_loyalty_tier=os.getenv("INFA_FIELD_LOYALTY_TIER", "").strip(),
            infa_field_preferred_regions=os.getenv("INFA_FIELD_PREFERRED_REGIONS", "").strip(),
            infa_field_preferred_suite=os.getenv("INFA_FIELD_PREFERRED_SUITE", "").strip(),
            infa_field_interest_focus=os.getenv("INFA_FIELD_INTEREST_FOCUS", "").strip(),
            infa_field_consent=os.getenv("INFA_FIELD_CONSENT", "").strip(),
            infa_field_vip=os.getenv("INFA_FIELD_VIP", "").strip(),
            infa_field_open_complaint=os.getenv("INFA_FIELD_OPEN_COMPLAINT", "").strip(),
            demo_assume_personalization_consent=parse_bool(
                os.getenv("DEMO_ASSUME_PERSONALIZATION_CONSENT", "false"), False
            ),
            secret_key=os.getenv("SECRET_KEY", "").strip(),
            demo_password=os.getenv("DEMO_PASSWORD", ""),
            allowed_origins=allowed_origins,
            chat_db_path=resolve_path("CHAT_DB_PATH", "data/chat.db"),
            chat_retention_days=parse_int("CHAT_RETENTION_DAYS", 30),
        )


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logger for clean server diagnostics."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("rcyc_concierge")


settings = Settings.from_env()
logger = configure_logging(settings.log_level)
