from functools import lru_cache
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./aiops.db'
    aiops_api_token: str = ''
    gateway_url: str = 'http://127.0.0.1:8091'
    gateway_token: str = ''
    gateway_approval_secret: str = ''
    llm_provider: Literal['ollama', 'gemini'] = 'ollama'
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_model: str = 'qwen2.5:3b'
    ollama_embedding_model: str = 'nomic-embed-text'
    ollama_num_ctx: int = Field(8192, ge=2048, le=32768)
    ollama_num_predict: int = Field(1200, ge=128, le=4096)
    ollama_num_thread: int = Field(3, ge=1, le=32)
    ollama_keep_alive: str = '5m'
    gemini_api_key: SecretStr = SecretStr('')
    gemini_base_url: str = 'https://generativelanguage.googleapis.com/v1beta'
    gemini_model: str = 'gemini-3.8-flash'
    gemini_thinking_level: Literal['low', 'medium', 'high'] = 'low'
    gemini_max_output_tokens: int = Field(4096, ge=512, le=65536)
    qdrant_url: str = 'http://127.0.0.1:6333'
    qdrant_api_key: str = ''
    qdrant_collection: str = 'homeai_knowledge'
    rag_enabled: bool = True
    rag_score_threshold: float = Field(0.45, ge=0, le=1)
    rag_top_k: int = Field(4, ge=1, le=10)
    topology_path: str = 'config/topology.json'
    runbooks_path: str = 'runbooks'
    agent_max_steps: int = Field(18, ge=1, le=30)
    agent_max_runtime_seconds: int = Field(900, ge=1, le=3600)
    agent_tool_timeout_seconds: int = Field(15, ge=1, le=60)
    agent_write_timeout_seconds: int = Field(35, ge=30, le=120)
    agent_llm_timeout_seconds: int = Field(180, ge=1, le=600)
    agent_context_chars: int = Field(26000, ge=4000, le=80000)
    agent_max_parallel_incidents: int = Field(1, ge=1, le=4)
    approval_ttl_seconds: int = Field(3600, ge=60, le=86400)
    enable_write_actions: bool = False
    disk_warning_percent: float = 80
    disk_high_percent: float = 90
    disk_critical_percent: float = 95

    def topology(self) -> dict:
        from .topology import load_topology
        return load_topology(self.topology_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
