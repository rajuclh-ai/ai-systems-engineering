"""Central configuration — reads from environment / .env file."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 600

    # ArXiv
    rss_categories: dict[str, str] = {
        "cs.AI": "https://arxiv.org/rss/cs.AI",
        "cs.LG": "https://arxiv.org/rss/cs.LG",
    }
    max_papers_per_feed: int = 15

    # Storage
    papers_dir: Path = BASE_DIR / "papers"
    chroma_dir: Path = BASE_DIR / "chroma_db"
    seen_manifest: Path = BASE_DIR / "papers" / "seen.json"

    # Chunking
    chunk_size: int = 300
    chunk_overlap: int = 30

    # Retrieval
    top_k: int = 5

    # Embedding model
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_collection: str = "arxiv_papers"


settings = Settings()
