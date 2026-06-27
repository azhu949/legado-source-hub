"""书源 Pydantic 数据模型。"""

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.legado import normalize_source_dict


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuleSearch(BaseModel):
    """搜索提取规则。"""

    bookList: str = ""
    name: str = ""
    author: str = ""
    kind: Optional[str] = ""
    lastChapter: Optional[str] = ""
    intro: Optional[str] = ""
    coverUrl: Optional[str] = ""
    noteUrl: Optional[str] = ""
    wordCount: Optional[str] = ""


class RuleBookInfo(BaseModel):
    """书籍详情提取规则。"""

    name: str = ""
    author: str = ""
    kind: Optional[str] = ""
    lastChapter: Optional[str] = ""
    wordCount: Optional[str] = ""
    intro: Optional[str] = ""
    coverUrl: Optional[str] = ""
    tocUrl: str = ""


class RuleToc(BaseModel):
    """章节目录提取规则。"""

    chapterList: str = ""
    chapterName: str = ""
    chapterUrl: str = ""


class RuleContent(BaseModel):
    """正文提取规则。"""

    content: str = ""


class BookSourceBase(BaseModel):
    """书源基础字段。"""

    bookSourceName: str = Field(..., min_length=1, max_length=50, description="书源名称")
    bookSourceGroup: str = Field(default="未分组", max_length=50, description="书源分组")
    bookSourceUrl: str = Field(..., min_length=1, description="源站基础URL")
    enabled: bool = True
    weight: int = Field(default=100, ge=0, le=9999, description="权重")
    searchUrl: str = Field(default="", description="搜索URL模板")
    ruleSearch: RuleSearch = Field(default_factory=RuleSearch)
    ruleBookInfo: RuleBookInfo = Field(default_factory=RuleBookInfo)
    ruleToc: RuleToc = Field(default_factory=RuleToc)
    ruleContent: RuleContent = Field(default_factory=RuleContent)
    headers: Optional[dict[str, str]] = Field(default=None, description="自定义请求头")

    @model_validator(mode="before")
    @classmethod
    def normalize_legado_source(cls, data):
        return normalize_source_dict(data)

    @field_validator("bookSourceUrl", "searchUrl", mode="before")
    @classmethod
    def strip_url(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class BookSourceCreate(BookSourceBase):
    """创建书源时的请求体。"""

    pass


class BookSourceUpdate(BookSourceBase):
    """更新书源时的请求体。"""

    pass


class BookSource(BookSourceBase):
    """完整书源模型（含系统字段）。"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    createdAt: str = Field(default_factory=_utcnow)
    updatedAt: str = Field(default_factory=_utcnow)

    def to_storage_dict(self) -> dict:
        """转为存储到 JSON 文件的字典（不含 id 文件名已使用）。"""
        data = self.model_dump()
        return data


class BookSourceBrief(BaseModel):
    """书源简要信息（列表/概览用）。"""

    id: str
    bookSourceName: str
    bookSourceGroup: str
    bookSourceUrl: str
    enabled: bool
    weight: int
    searchUrl: str


class HealthStatus(BaseModel):
    """书源健康状态。"""

    id: str
    bookSourceName: str
    status: str = "unknown"  # healthy / unhealthy / unknown
    latency_ms: Optional[int] = None
    last_check: Optional[str] = None
    consecutive_failures: int = 0


class TestRuleRequest(BaseModel):
    """规则测试请求。"""

    testUrl: str = Field(default="", description="待测试的URL")
    rules: dict = Field(..., description="规则字典")
    isJson: bool = False
    sourceId: Optional[str] = None


class ImportSourceRequest(BaseModel):
    """批量导入书源请求。"""

    sources: list[dict] = Field(..., description="书源JSON数组")
    conflictStrategy: str = Field(
        default="skip", description="冲突策略: skip/overwrite/new"
    )


class ImportUrlRequest(BaseModel):
    """从URL导入书源请求。"""

    url: str = Field(..., description="远程书源JSON地址")
    conflictStrategy: str = Field(default="skip")


class ToggleSourceRequest(BaseModel):
    """启禁用书源请求。"""

    enabled: bool


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应。"""

    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in: int
