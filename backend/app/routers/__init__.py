"""路由包导出：集中管理 API Router。"""

from .memory import router as memory_router
from .plugins import router as plugins_router
from .storage import router as storage_router

__all__ = ["storage_router", "memory_router", "plugins_router"]
