from functools import lru_cache
from typing import Optional, Any
from pydantic_settings import BaseSettings
from dataclasses import dataclass, field, fields
from dotenv import load_dotenv
from langchain_core.runnables import RunnableConfig
import os

# Cargar las variables del archivo .env
load_dotenv()


@dataclass(kw_only=True)
class LangGraphConfig:
    """Configuración específica para LangGraph"""
    number_of_queries: int = 2
    tavily_topic: str = "general"
    tavily_days: str = None

    @classmethod
    def from_runnable_config(
            cls, config: Optional[RunnableConfig] = None
    ) -> "LangGraphConfig":
        """Crear configuración desde RunnableConfig de LangGraph"""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )
        values: dict[str, Any] = {
            f.name: os.environ.get(f.name.upper(), configurable.get(f.name))
            for f in fields(cls)
            if f.init
        }
        return cls(**{k: v for k, v in values.items() if v})


class Settings(BaseSettings):
    tavily_api_key: str
    openai_api_key: str
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    mistral_api_key: str

    # Database Configuration
    db_name: str
    db_user: str
    db_password: str
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # Environment
    environment: str = "development"

    # REDIS_HOST=redis
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = "123456"

    # LangSmith
    langsmith_tracing: bool = True
    langsmith_api_key: str
    langsmith_endpoint: str
    langsmith_project: str

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
