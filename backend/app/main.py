"""FastAPI 应用入口：初始化数据库、注册路由与基础中间件。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .db import engine
from .models import Base
from .routers import memory_router, plugins_router, storage_router

settings = get_settings()

app = FastAPI(
    title="RP-Hub Backend",
    version="1.0.0",
    description="RP-Hub 后端化存储服务（PostgreSQL + Qdrant + 插件接口）",
)

# CORS：允许前端（含 file:// 调试）调用后端 API。
if settings.cors_origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def on_startup() -> None:
    """启动时自动建表（轻量方案，后续可替换为 Alembic 迁移）。"""
    Base.metadata.create_all(bind=engine)


@app.get("/healthz")
def healthz():
    """健康检查接口。"""
    return {"ok": True, "env": settings.app_env}


app.include_router(storage_router)
app.include_router(memory_router)
app.include_router(plugins_router)

# 前端静态资源根目录（RP-Hub 项目根目录）
FRONTEND_ROOT = Path(__file__).resolve().parents[2]

# 仅暴露必要静态目录，避免将整个仓库公开为静态文件。
app.mount("/assets", StaticFiles(directory=str(FRONTEND_ROOT / "assets")), name="assets")
app.mount("/character", StaticFiles(directory=str(FRONTEND_ROOT / "character"), html=True), name="character")


@app.get("/", include_in_schema=False)
def frontend_index():
    """返回前端首页。"""
    return FileResponse(FRONTEND_ROOT / "index.html")


@app.get("/index.html", include_in_schema=False)
def frontend_index_alias():
    """兼容直接访问 /index.html。"""
    return FileResponse(FRONTEND_ROOT / "index.html")
