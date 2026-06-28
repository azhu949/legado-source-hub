"""应用配置管理。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，通过环境变量覆盖默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用基础
    APP_NAME: str = "聚合书源管理系统"
    APP_DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 数据目录
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data"
    SOURCES_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "sources"
    DB_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "logs.db"
    RUNTIME_LOG_PATH: Path = Path(__file__).resolve().parent.parent / "data" / "logs" / "backend.log"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SEARCH: int = 3600  # 搜索结果缓存 1 小时
    CACHE_TTL_BOOK: int = 86400
    CACHE_TTL_TOC: int = 86400

    # 认证
    ADMIN_USER: str = "admin"
    ADMIN_PASS: str = "admin123"
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # HTTP 客户端
    HTTP_TIMEOUT: int = 15
    HTTP_RETRIES: int = 2
    HTTP_USER_AGENT: str = (
        "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )

    # 健康检查
    HEALTH_CHECK_INTERVAL: int = 30  # 分钟
    HEALTH_FAIL_THRESHOLD: int = 3

    # 日志
    LOG_LEVEL: str = "INFO"

    def ensure_dirs(self) -> None:
        """确保运行所需目录存在。"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.RUNTIME_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
