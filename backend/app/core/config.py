"""
Application settings.

All configuration comes from environment variables (prefix ``CD_``) or a ``.env`` file, so the
same image runs in dev, CI and production without code changes. Nothing secret is hard-coded:
the defaults below are only safe for local development.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings object. Read once per process via :func:`get_settings`."""

    model_config = SettingsConfigDict(env_prefix="CD_", env_file=".env", extra="ignore")

    # --- Storage ---------------------------------------------------------------------------------
    # Root for everything the service writes: the SQLite database, generated data, the Claude cache.
    data_dir: Path = Path("./data")
    # SQLAlchemy URL for the application database. Defaults to SQLite inside data_dir.
    # For Postgres use e.g. postgresql+psycopg://user:pass@host:5432/capital_drift
    database_url: str | None = None

    # --- Invoice matching with Claude (app/llm/invoice_llm.py) ------------------------------------
    # "anthropic" (Claude API; ANTHROPIC_API_KEY or an `ant auth login` profile) or "bedrock"
    # (Amazon Bedrock through the Mantle client; AWS credentials and match_llm_aws_region).
    match_llm_provider: str = "anthropic"
    # Claude API model id; on Bedrock the same id with an "anthropic." prefix is used.
    match_llm_model: str = "claude-opus-5-5"
    match_llm_aws_region: str = "us-east-1"
    # Classification is a short task: low effort keeps thinking and cost down.
    match_llm_effort: str = "low"
    match_llm_max_tokens: int = 4000
    # Hard cap on live calls per run. Small by default so nothing large runs by accident.
    match_llm_max_calls: int = 10
    # Prices for the cost estimate in the run summary (USD per million tokens, first-party rates).
    match_llm_input_price: float = 4.0
    match_llm_output_price: float = 20.0
    # Responses are cached here by prompt hash, so re-scoring or re-running never pays twice.
    match_llm_cache_file: str = "llm_cache/invoice_matches.jsonl"
    # Offline evaluation results (synthetic data) for the results page; tracked in git, written by `cli results`.
    capital_results_file: Path = Path(__file__).resolve().parents[2] / "results" / "capital_results.json"

    # --- Security --------------------------------------------------------------------------------
    # Demo bearer tokens: "token:username:role,...". Replace with SSO/OIDC before any real use.
    auth_tokens: str = Field(
        default="board-token:bea:board_member,manager-token:max:property_manager,admin-token:adam:admin"
    )
    # Browser origins allowed to call the API (the React dev server by default).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    log_level: str = "INFO"
    log_json: bool = False

    # --- Derived paths ---------------------------------------------------------------------------
    @property
    def resolved_database_url(self) -> str:
        """App DB URL, defaulting to a SQLite file in ``data_dir``."""
        return self.database_url or f"sqlite:///{(self.data_dir / 'capital_drift.db').resolve()}"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, creating the data directories on first use."""
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
