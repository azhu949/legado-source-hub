"""FastAPI 应用入口。"""

import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.core.cache import cache
from app.core.health_checker import health_checker
from app.core.http_client import http_client
from app.core.source_manager import source_manager
from app.models.database import init_db
from app.utils.public_url import get_public_origin

# 日志配置
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    logger.info("启动聚合书源管理系统...")

    # 初始化数据库
    init_db()
    logger.info("数据库已初始化")

    # 加载书源
    source_manager.load_all()

    # 连接缓存
    await cache.connect()

    # 启动定时健康检查
    health_checker.start_periodic()

    logger.info("系统启动完成")
    yield

    # 关闭
    logger.info("正在关闭系统...")
    health_checker.stop_periodic()
    await cache.close()
    await http_client.close()
    logger.info("系统已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="聚合书源管理系统后端 API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_router)


@app.get("/api/aggregate_source.json")
async def get_aggregate_source(request: Request):
    """对外聚合书源定义（供阅读 APP 直接导入）。"""
    host = get_public_origin(request)
    # Legado/阅读 APP 的网络导入入口按书源列表解析，即使只有一个书源也需要数组根节点。
    return JSONResponse(content=[_build_public_book_source(host)])


def _build_public_book_source(host: str) -> dict:
    source = {
        "bookSourceName": "📚 聚合书源·Pro",
        "bookSourceGroup": "聚合",
        "bookSourceComment": (
            "单书源动态聚合：默认返回分源候选，详情中的真实来源会显示在分类、最新章节和简介中。"
            "可在登录/书源设置中填写搜索来源，也可直接搜索「书名@来源」。"
        ),
        "bookSourceUrl": host,
        "bookSourceType": 0,
        "enabled": True,
        "weight": 999,
        "bookUrlPattern": r"https?:\/\/(?:[a-zA-Z0-9.-]+)(?::\d+)?\/api\/book.*",
        "enabledCookieJar": False,
        "jsLib": _build_public_source_js_lib(),
        "loginUi": _build_public_source_login_ui(),
        "searchUrl": _build_public_source_search_url(),
        "ruleSearch": {
            "bookList": "$.data[*]",
            "name": "$.name",
            "author": "$.author",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "intro": "$.intro",
            "coverUrl": "$.coverUrl",
            "noteUrl": "$.noteUrl",
            "bookUrl": "$.bookUrl",
            "wordCount": "$.wordCount",
        },
        "ruleBookInfo": {
            "name": "$.data.name",
            "author": "$.data.author",
            "kind": "$.data.kind",
            "lastChapter": "$.data.lastChapter",
            "wordCount": "$.data.wordCount",
            "intro": "$.data.intro",
            "coverUrl": "$.data.coverUrl",
            "tocUrl": "$.data.tocUrl",
        },
        "ruleToc": {
            "chapterList": "$.data[*]",
            "chapterName": "$.name",
            "chapterUrl": "$.url",
        },
        "ruleContent": {"content": "$.data.content"},
    }
    explore_urls = _build_public_explore_urls(host)
    if explore_urls:
        source["enabledExplore"] = True
        source["exploreUrl"] = explore_urls
        source["ruleExplore"] = {
            "bookList": "$.data.books[*]",
            "name": "$.name",
            "author": "$.author",
            "kind": "$.kind",
            "lastChapter": "$.lastChapter",
            "intro": "$.intro",
            "coverUrl": "$.coverUrl",
            "noteUrl": "$.noteUrl",
            "bookUrl": "$.bookUrl",
            "tocUrl": "$.tocUrl",
            "wordCount": "$.wordCount",
            "nextUrl": "$.data.nextUrl",
        }
    return source


def _build_public_explore_urls(host: str) -> list[str]:
    entries: list[str] = []
    try:
        sources = source_manager.get_enabled_sources()
    except Exception:  # noqa: BLE001
        return entries

    for src in sources:
        rule_explore = getattr(src, "ruleExplore", None)
        if not getattr(src, "enabledExplore", False) or not getattr(rule_explore, "bookList", ""):
            continue
        for label, url in _iter_explore_entries(getattr(src, "exploreUrl", None)):
            display = f"{src.bookSourceName}/{label}" if label else src.bookSourceName
            params = urlencode({"url": url, "sourceId": src.id})
            entries.append(f"{display}::{host.rstrip('/')}/api/explore?{params}")
    return entries


def _iter_explore_entries(explore_url) -> list[tuple[str, str]]:
    values: list[str] = []
    if isinstance(explore_url, list):
        values = [str(item) for item in explore_url]
    elif isinstance(explore_url, str):
        values = [item.strip() for item in explore_url.splitlines() if item.strip()]

    entries: list[tuple[str, str]] = []
    for item in values:
        label, separator, url = item.partition("::")
        if separator:
            entries.append((label.strip(), url.strip()))
        else:
            entries.append(("", item.strip()))
    return [(label, url) for label, url in entries if url]


def _build_public_source_search_url() -> str:
    return """<js>
const settings = aggSettings();
let searchKey = String(key || '').trim();
let sourceName = String(settings['搜索来源'] || '全部').trim();
const atIndex = Math.max(searchKey.lastIndexOf('@'), searchKey.lastIndexOf('＠'));
if (atIndex > 0 && atIndex < searchKey.length - 1) {
    sourceName = searchKey.slice(atIndex + 1).trim();
    searchKey = searchKey.slice(0, atIndex).trim();
}
if (!sourceName) sourceName = '全部';
const mode = String(settings['结果模式'] || '分源');
const merge = mode === '聚合' || mode === '聚合去重' || mode === '1' ? '1' : '0';
`${aggBaseUrl()}/api/search?keyword=${encodeURIComponent(searchKey)}&page=${page || 1}&merge=${merge}&source=${encodeURIComponent(sourceName)}`;
</js>"""


def _build_public_source_js_lib() -> str:
    return """function aggBaseUrl() {
    let key = '';
    try { key = source.getKey ? source.getKey() : source.key; } catch (e) {}
    key = String(key || '').replace(/\\/+$/, '');
    return key;
}

function aggSettings() {
    try {
        const raw = source.getVariable ? source.getVariable() : '';
        return raw ? JSON.parse(raw) : {};
    } catch (e) {
        return {};
    }
}

function aggSaveSettings(settings) {
    source.setVariable(JSON.stringify(settings || {}, null, 2));
}

function aggSetSearchSource() {
    const settings = aggSettings();
    const value = result['搜索来源(全部/书源名/ID，多个用英文逗号)'] || '全部';
    settings['搜索来源'] = String(value || '全部').trim() || '全部';
    aggSaveSettings(settings);
    java.toast('搜索来源：' + settings['搜索来源']);
}

function aggSetMergeMode(mode) {
    const settings = aggSettings();
    settings['结果模式'] = mode;
    aggSaveSettings(settings);
    java.toast('结果模式：' + mode);
}

function aggShowSettings() {
    const settings = aggSettings();
    java.longToast('当前设置\\n搜索来源：' + (settings['搜索来源'] || '全部') + '\\n结果模式：' + (settings['结果模式'] || '分源'));
}

function aggClearSettings() {
    aggSaveSettings({});
    java.toast('聚合书源设置已清空');
}"""


def _build_public_source_login_ui() -> str:
    return json.dumps(
        [
            {
                "name": "搜索来源(全部/书源名/ID，多个用英文逗号)",
                "type": "text",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 1},
            },
            {
                "name": "设置搜索来源",
                "type": "button",
                "action": "aggSetSearchSource()",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 0.5},
            },
            {
                "name": "分源结果",
                "type": "button",
                "action": "aggSetMergeMode('分源')",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 0.5},
            },
            {
                "name": "聚合去重",
                "type": "button",
                "action": "aggSetMergeMode('聚合')",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 0.5},
            },
            {
                "name": "查看当前设置",
                "type": "button",
                "action": "aggShowSettings()",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 0.5},
            },
            {
                "name": "清空设置",
                "type": "button",
                "action": "aggClearSettings()",
                "style": {"layout_flexGrow": 1, "layout_flexBasisPercent": 1},
            },
        ],
        ensure_ascii=False,
    )


# 前端静态资源挂载（生产环境由 Nginx 处理，开发态可挂载）
_frontend_dist = settings.BASE_DIR.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/admin", StaticFiles(directory=str(_frontend_dist), html=True), name="admin")
    logger.info("已挂载前端静态资源: %s", _frontend_dist)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理。"""
    logger.error("未处理异常: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.APP_DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
