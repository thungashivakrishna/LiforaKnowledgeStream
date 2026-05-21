from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    db: str = Field(default="knowledge_stream")
    user: str = Field(default="ks_user")
    password: str = Field(default="ks_password")
    pool_size: int = Field(default=10)
    max_overflow: int = Field(default=20)

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class QdrantSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QDRANT_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=6333)
    collection_name: str = Field(default="knowledge_chunks")
    api_key: str | None = Field(default=None)
    url: str | None = Field(default=None)


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEO4J_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    bolt_port: int = Field(default=7687)
    user: str = Field(default="neo4j")
    password: str = Field(default="ks_password")

    @property
    def uri(self) -> str:
        return f"bolt://{self.host}:{self.bolt_port}"


class MinioSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MINIO_", env_file=".env", extra="ignore")

    endpoint: str = Field(default="localhost:9000")
    access_key: str = Field(default="minioadmin")
    secret_key: str = Field(default="minioadmin")
    secure: bool = Field(default=False)
    bucket_raw: str = Field(default="raw-artifacts")
    bucket_extracted: str = Field(default="extracted-text")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=6379)
    db: int = Field(default=0)

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


class TemporalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TEMPORAL_", env_file=".env", extra="ignore")

    host: str = Field(default="localhost")
    port: int = Field(default=7233)
    namespace: str = Field(default="default")
    task_queue: str = Field(default="knowledge-stream-queue")

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"


class ModelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # Primary: DeepSeek V3
    primary_model: str = Field(default="deepseek/deepseek-chat", alias="MODEL_PRIMARY")
    primary_api_key: str = Field(default="", alias="MODEL_PRIMARY_API_KEY")
    primary_api_base: str = Field(default="https://api.deepseek.com", alias="MODEL_PRIMARY_API_BASE")

    # Secondary: Gemini
    secondary_model: str = Field(default="gemini/gemini-1.5-pro", alias="MODEL_SECONDARY")
    secondary_api_key: str = Field(default="", alias="MODEL_SECONDARY_API_KEY")

    # Tertiary: OpenAI
    tertiary_model: str = Field(default="gpt-4o-mini", alias="MODEL_TERTIARY")
    tertiary_api_key: str = Field(default="", alias="MODEL_TERTIARY_API_KEY")

    # Embedding (configurable — finalized before Batch 5)
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_dimensions: int = Field(default=1536, alias="EMBEDDING_DIMENSIONS")

    confidence_fallback_threshold: float = Field(default=0.6, alias="MODEL_CONFIDENCE_THRESHOLD")
    max_retries: int = Field(default=3, alias="MODEL_MAX_RETRIES")

    # Gateway routing chains (comma-separated model strings)
    fallback_chain_csv: str = Field(
        default="deepseek/deepseek-chat,gemini/gemini-1.5-pro,gpt-4o-mini",
        alias="LLM_FALLBACK_CHAIN",
    )
    fast_chain_csv: str = Field(
        default="gpt-4o-mini,gemini/gemini-1.5-flash",
        alias="LLM_FAST_CHAIN",
    )

    # Budget enforcement
    daily_budget_usd: float = Field(default=50.0, alias="LLM_DAILY_BUDGET_USD")
    per_doc_budget_usd: float = Field(default=0.5, alias="LLM_PER_DOC_BUDGET_USD")
    budget_enforcement: str = Field(default="soft", alias="LLM_BUDGET_ENFORCEMENT")

    # Prompt response cache TTL
    prompt_cache_ttl_seconds: int = Field(default=2_592_000, alias="LLM_PROMPT_CACHE_TTL_SECONDS")

    # Safety
    redact_pii: bool = Field(default=True, alias="LLM_REDACT_PII")

    @property
    def fallback_chain(self) -> list[str]:
        return [m.strip() for m in self.fallback_chain_csv.split(",") if m.strip()]

    @property
    def fast_chain(self) -> list[str]:
        return [m.strip() for m in self.fast_chain_csv.split(",") if m.strip()]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = Field(default="Lifora Knowledge Stream API", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")
    admin_secret: str = Field(default="change-me-in-production", alias="ADMIN_SECRET")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app: AppSettings = Field(default_factory=AppSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    temporal: TemporalSettings = Field(default_factory=TemporalSettings)
    model: ModelSettings = Field(default_factory=ModelSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()
