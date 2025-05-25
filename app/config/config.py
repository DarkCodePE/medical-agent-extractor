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
    # API Keys - Optional with None defaults
    tavily_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    mistral_api_key: Optional[str] = None

    # Database Configuration - PostgreSQL (consistent with database.py)
    db_host: str = "localhost"
    db_port: str = "5432"
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # SQL Server Database Configuration (for GTIN service)
    db_server: Optional[str] = None  # SQL Server host
    db_type: Optional[str] = "sqlserver"
    db_connection_string: Optional[str] = None

    # Environment
    environment: str = "development"

    # Redis Configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None

    # LangSmith Configuration
    langsmith_tracing: bool = False
    langsmith_api_key: Optional[str] = None
    langsmith_endpoint: Optional[str] = None
    langsmith_project: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra fields for flexibility
        extra = "allow"


@lru_cache()
def get_settings():
    return Settings()
