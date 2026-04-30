"""ORM 模型定义：主存储键值表、插件表。"""

import uuid

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AppKV(Base):
    """应用主存储键值表。

    说明：
    - namespace 用于用户隔离（例如用户 UUID）。
    - key 对齐前端原有 IndexedDB key（如 silly_tavern_chat_xxx）。
    - value 使用 JSON，承载任意结构化数据。
    """

    __tablename__ = "app_kv"

    namespace = Column(String(128), primary_key=True)
    key = Column(String(255), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class PluginConfig(Base):
    """插件配置表。

    type 支持：
    - http: 调用外部 HTTP API
    - bluetooth: 调用蓝牙动作（基于 bleak）
    """

    __tablename__ = "plugin_config"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(128), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    type = Column(String(40), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    config = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class MemoryVectorMeta(Base):
    """记忆向量元信息表。

    说明：
    - 详细向量存储在 Qdrant。
    - 本表用于追踪记忆与角色归属，以及便于回表展示。
    """

    __tablename__ = "memory_vector_meta"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    character_uuid = Column(String(64), nullable=False, index=True)
    category = Column(String(32), nullable=False)
    turn = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
