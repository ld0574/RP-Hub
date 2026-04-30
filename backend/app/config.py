"""后端配置模块：统一读取环境变量，并提供类型化配置对象。"""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置对象。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")

    database_url: str = Field(
        default="postgresql+psycopg2://rphub:rphub@127.0.0.1:5432/rphub",
        alias="DATABASE_URL",
    )

    qdrant_url: str = Field(default="http://127.0.0.1:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="rp_hub_memories", alias="QDRANT_COLLECTION")
    embedding_dim: int = Field(default=1536, alias="EMBEDDING_DIM")

    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    @property
    def cors_origins(self) -> List[str]:
        """将逗号分隔配置解析成列表。"""
        raw = (self.cors_origins_raw or "*").strip()
        if raw == "*":
            return ["*"]
        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回单例配置，避免重复解析环境变量。"""
    return Settings()
