"""Root dotenv settings; credentials never leave the backend."""
from pathlib import Path
from typing import Literal
from pydantic import SecretStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    openrouter_api_key: SecretStr = SecretStr("")
    gradium_api_key: SecretStr = SecretStr("")
    gradium_voice_id: str = "YTpq7expH9539ERJ"
    llm_model: str = Field(default="meta/muse-spark-1.3-contributor", min_length=1)
    resoning_lvl: Literal["xhigh", "high", "medium", "low", "minimal", "none"] = "low"
    checkpoint_path: str = "data/runtime/chat-checkpoints.sqlite3"

    @property
    def db_path(self) -> Path:
        path = Path(self.checkpoint_path)
        return path if path.is_absolute() else ROOT / path
