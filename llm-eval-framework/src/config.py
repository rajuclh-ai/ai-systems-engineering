"""Central configuration — reads from environment / .env and eval_config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    # Path to arxiv-expert-rag so its pipeline can be imported
    rag_project_path: str = str(BASE_DIR.parent / "arxiv-expert-rag")
    # Path to pr_review_agent so its pipeline can be imported
    agent_project_path: str = str(BASE_DIR.parent / "pr_review_agent" / "src")


settings = Settings()


class EvalConfig:
    """Parsed eval_config.yaml."""

    def __init__(self, path: str | Path = BASE_DIR / "eval_config.yaml") -> None:
        with open(path) as f:
            raw = yaml.safe_load(f)

        self.model: str = raw["model"]
        self.temperature: int = raw.get("temperature", 0)

        rag = raw.get("rag", {})
        self.rag_dataset: Path = BASE_DIR / rag.get("dataset", "datasets/arxiv_rag_testset.json")
        self.rag_generate_n: int = rag.get("generate_n", 10)
        self.rag_thresholds: dict[str, float] = rag.get("thresholds", {})

        agent = raw.get("agent", {})
        self.agent_dataset: Path = BASE_DIR / agent.get("dataset", "datasets/pr_agent_testset.json")
        self.agent_thresholds: dict[str, float] = agent.get("thresholds", {})
