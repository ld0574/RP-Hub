"""Pydantic 数据模型：用于请求与响应结构校验。"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class StorageSetRequest(BaseModel):
    """键值写入请求。"""

    value: Any


class StorageGetResponse(BaseModel):
    """键值读取响应。"""

    found: bool
    value: Any = None


class StorageDeleteResponse(BaseModel):
    """键值删除响应。"""

    deleted: bool


class MemoryUpsertRequest(BaseModel):
    """记忆向量写入请求。"""

    memory_id: str = Field(..., min_length=1)
    character_uuid: str = Field(..., min_length=1)
    category: str = Field(default="event")
    turn: int = 0
    summary: str = Field(..., min_length=1)
    embedding: List[float] = Field(..., min_items=8)
    payload: Dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    """记忆向量检索请求。"""

    character_uuid: str = Field(..., min_length=1)
    embedding: List[float] = Field(..., min_items=8)
    limit: int = Field(default=12, ge=1, le=100)
    score_threshold: float = Field(default=0.2, ge=-1.0, le=1.0)


class MemorySearchItem(BaseModel):
    """记忆检索条目。"""

    memory_id: str
    score: float
    category: str
    turn: int
    summary: str
    payload: Dict[str, Any]


class MemorySearchResponse(BaseModel):
    """记忆检索响应。"""

    items: List[MemorySearchItem]


class PluginCreateRequest(BaseModel):
    """插件创建请求。"""

    name: str = Field(..., min_length=1, max_length=120)
    type: Literal["http", "bluetooth"]
    description: Optional[str] = None
    enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)


class PluginResponse(BaseModel):
    """插件响应结构。"""

    id: str
    name: str
    type: str
    description: Optional[str]
    enabled: bool
    config: Dict[str, Any]


class PluginInvokeRequest(BaseModel):
    """插件调用请求。

    action 为插件动作名，例如：
    - HTTP 插件："request"
    - Bluetooth 插件："scan" / "write_gatt"
    """

    action: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


class PluginInvokeResponse(BaseModel):
    """插件调用响应。"""

    ok: bool
    output: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
