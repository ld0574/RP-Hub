"""ORM 模型定义。

当前采用“双层架构”：
1) 兼容层：`app_kv`（保持前端现有 key-value 读写逻辑不破坏）
2) 领域层：用户/角色/会话/消息/记忆/插件等规范化表（用于后续功能扩展）

说明：
- 现阶段前端仍主要通过 `app_kv` 读写。
- 新增的规范化表已可建表，后续可以逐步把业务切过去。
"""

import uuid

from sqlalchemy import JSON, BigInteger, Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TimestampMixin:
    """通用时间戳字段混入。"""

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


# =========================
# 兼容层（当前正在使用）
# =========================


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


class MemoryVectorMeta(Base, TimestampMixin):
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
    payload = Column(JSON, nullable=False, default=lambda: {})


class PluginConfig(Base, TimestampMixin):
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
    config = Column(JSON, nullable=False, default=lambda: {})


# =========================
# 领域层（为后续扩展预建）
# =========================


class UserNamespace(Base, TimestampMixin):
    """用户命名空间表：用于多用户隔离与账号标识。"""

    __tablename__ = "user_namespace"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(128), nullable=False, unique=True, index=True)
    display_name = Column(String(120), nullable=True)
    meta = Column(JSON, nullable=False, default=lambda: {})


class UserProfile(Base, TimestampMixin):
    """用户人设表：映射前端 userProfiles 概念。"""

    __tablename__ = "user_profile"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace = Column(String(128), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    avatar = Column(Text, nullable=True)
    person = Column(String(16), nullable=False, default="second")
    is_active = Column(Boolean, nullable=False, default=False)
    meta = Column(JSON, nullable=False, default=lambda: {})


class Character(Base, TimestampMixin):
    """角色主表：存储角色核心字段与扩展 JSON。"""

    __tablename__ = "character"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    name = Column(String(120), nullable=False, index=True)
    description = Column(Text, nullable=True)
    personality = Column(Text, nullable=True)
    scenario = Column(Text, nullable=True)
    first_mes = Column(Text, nullable=True)
    mes_example = Column(Text, nullable=True)
    avatar = Column(Text, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    raw_card = Column(JSON, nullable=False, default=lambda: {})


class ChatSession(Base, TimestampMixin):
    """会话表：一条会话通常对应一个角色的一段聊天历史。"""

    __tablename__ = "chat_session"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    character_id = Column(String(64), nullable=False, index=True)
    title = Column(String(160), nullable=True)
    source = Column(String(32), nullable=False, default="manual")
    meta = Column(JSON, nullable=False, default=lambda: {})


class ChatMessage(Base):
    """消息表：会话中的逐条消息（可选带推理文本）。"""

    __tablename__ = "chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(String(64), nullable=False, index=True)
    turn = Column(Integer, nullable=False, default=0, index=True)
    role = Column(String(16), nullable=False, index=True)
    speaker_name = Column(String(120), nullable=True)
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True)
    meta = Column(JSON, nullable=False, default=lambda: {})
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MemoryRecord(Base, TimestampMixin):
    """规范化记忆表：用于和 Qdrant 向量记录形成“一主一索引”结构。"""

    __tablename__ = "memory_record"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    character_id = Column(String(64), nullable=False, index=True)
    turn = Column(Integer, nullable=False, default=0, index=True)
    category = Column(String(32), nullable=False)
    summary = Column(Text, nullable=False)
    time_label = Column(String(64), nullable=True)
    location_label = Column(String(128), nullable=True)
    npcs = Column(JSON, nullable=False, default=lambda: [])
    depth = Column(Integer, nullable=False, default=3)
    enabled = Column(Boolean, nullable=False, default=True)
    meta = Column(JSON, nullable=False, default=lambda: {})


class PresetRecord(Base, TimestampMixin):
    """预设表：用于替代前端当前 presets JSON 全量存储。"""

    __tablename__ = "preset_record"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    content = Column(Text, nullable=False)
    order_no = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    meta = Column(JSON, nullable=False, default=lambda: {})


class RegexRecord(Base, TimestampMixin):
    """正则脚本表。"""

    __tablename__ = "regex_record"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    regex = Column(Text, nullable=False)
    flags = Column(String(32), nullable=True)
    replacement = Column(Text, nullable=True)
    placement = Column(JSON, nullable=False, default=lambda: [1, 2])
    markdown_only = Column(Boolean, nullable=False, default=False)
    prompt_only = Column(Boolean, nullable=False, default=False)
    enabled = Column(Boolean, nullable=False, default=True)
    order_no = Column(Integer, nullable=False, default=0)
    meta = Column(JSON, nullable=False, default=lambda: {})


class WorldInfoRecord(Base, TimestampMixin):
    """世界书条目表。"""

    __tablename__ = "worldinfo_record"

    id = Column(String(64), primary_key=True)
    namespace = Column(String(128), nullable=False, index=True)
    character_id = Column(String(64), nullable=True, index=True)
    name = Column(String(160), nullable=False)
    content = Column(Text, nullable=False)
    position = Column(String(32), nullable=False, default="at_depth")
    depth = Column(Integer, nullable=False, default=4)
    order_no = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    keys = Column(JSON, nullable=False, default=lambda: [])
    secondary_keys = Column(JSON, nullable=False, default=lambda: [])
    meta = Column(JSON, nullable=False, default=lambda: {})


class PluginInvocationLog(Base, TimestampMixin):
    """插件调用日志表：方便审计与排障。"""

    __tablename__ = "plugin_invocation_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    namespace = Column(String(128), nullable=False, index=True)
    plugin_id = Column(String(36), nullable=False, index=True)
    action = Column(String(80), nullable=False)
    success = Column(Boolean, nullable=False, default=True)
    request_payload = Column(JSON, nullable=False, default=lambda: {})
    response_payload = Column(JSON, nullable=False, default=lambda: {})
    error_message = Column(Text, nullable=True)
