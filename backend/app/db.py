"""数据库模块：创建 SQLAlchemy 引擎、会话工厂与依赖注入。"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()

# 数据库引擎：默认使用 PostgreSQL；也可通过 DATABASE_URL 切到其他数据库。
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)

# 会话工厂：统一由 FastAPI 路由依赖获取。
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：按请求生命周期提供数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_context() -> Iterator[Session]:
    """非路由场景下的数据库上下文辅助方法。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
