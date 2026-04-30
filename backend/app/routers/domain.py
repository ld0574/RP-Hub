"""领域数据路由：角色/聊天/记忆的规范化表读写接口。"""

import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Character, ChatMessage, ChatSession, MemoryRecord
from ..schemas import (
    CharacterBulkRequest,
    CharacterBulkResponse,
    ChatBulkRequest,
    ChatBulkResponse,
    MemoryBulkRequest,
    MemoryBulkResponse,
)
from .storage import resolve_namespace

router = APIRouter(prefix="/api/domain", tags=["domain"])


def _safe_str(value: Any, default: str = "") -> str:
    """将任意值转成字符串，避免 `None` 或复杂对象导致入库异常。"""
    if value is None:
        return default
    return str(value)


@router.get("/characters", response_model=CharacterBulkResponse)
def get_characters(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取当前命名空间下的全部角色。"""
    namespace = resolve_namespace(x_rph_user)
    rows = db.query(Character).filter(Character.namespace == namespace).order_by(Character.created_at.asc()).all()

    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.raw_card or {})
        if not raw:
            raw = {
                "uuid": row.id,
                "name": row.name,
                "description": row.description or "",
                "personality": row.personality or "",
                "scenario": row.scenario or "",
                "first_mes": row.first_mes or "",
                "mes_example": row.mes_example or "",
                "avatar": row.avatar or "",
            }
        if not raw.get("uuid"):
            raw["uuid"] = row.id
        items.append(raw)
    return CharacterBulkResponse(items=items)


@router.put("/characters", response_model=CharacterBulkResponse)
def put_characters(
    request: CharacterBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量写入角色列表（替换当前命名空间角色集合）。"""
    namespace = resolve_namespace(x_rph_user)
    incoming_ids: List[str] = []
    incoming_map: Dict[str, Dict[str, Any]] = {}

    for item in request.items:
        char_id = _safe_str(item.get("uuid"), "") or str(uuid.uuid4())
        normalized = dict(item)
        normalized["uuid"] = char_id
        incoming_ids.append(char_id)
        incoming_map[char_id] = normalized

    # 删除已不存在的角色
    if incoming_ids:
        db.query(Character).filter(Character.namespace == namespace, ~Character.id.in_(incoming_ids)).delete(synchronize_session=False)
    else:
        db.query(Character).filter(Character.namespace == namespace).delete(synchronize_session=False)

    # upsert 角色
    for char_id in incoming_ids:
        item = incoming_map[char_id]
        row = db.query(Character).filter(Character.namespace == namespace, Character.id == char_id).one_or_none()
        if row is None:
            row = Character(id=char_id, namespace=namespace)
            db.add(row)

        row.name = _safe_str(item.get("name"), "Unnamed")
        row.description = _safe_str(item.get("description"), "")
        row.personality = _safe_str(item.get("personality"), "")
        row.scenario = _safe_str(item.get("scenario"), "")
        row.first_mes = _safe_str(item.get("first_mes"), "")
        row.mes_example = _safe_str(item.get("mes_example"), "")
        row.avatar = _safe_str(item.get("avatar"), "")
        row.is_archived = bool(item.get("is_archived", False))
        row.raw_card = item

    db.commit()
    return CharacterBulkResponse(items=list(incoming_map.values()))


@router.get("/chat/{character_id}", response_model=ChatBulkResponse)
def get_chat_messages(
    character_id: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取某角色主会话消息。"""
    namespace = resolve_namespace(x_rph_user)
    session_id = f"{character_id}:main"

    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_id == session_id)
        .order_by(ChatMessage.turn.asc(), ChatMessage.id.asc())
        .all()
    )

    messages: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.meta or {}).get("raw") if isinstance(row.meta, dict) else None
        if isinstance(raw, dict):
            messages.append(raw)
            continue

        msg = {
            "role": row.role,
            "name": row.speaker_name,
            "content": row.content,
            "isSelf": row.role == "user",
        }
        if row.reasoning:
            msg["reasoning"] = row.reasoning
        messages.append(msg)

    return ChatBulkResponse(messages=messages)


@router.put("/chat/{character_id}", response_model=ChatBulkResponse)
def put_chat_messages(
    character_id: str,
    request: ChatBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量替换某角色主会话消息。"""
    namespace = resolve_namespace(x_rph_user)
    session_id = f"{character_id}:main"

    session_row = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.namespace == namespace).one_or_none()
    if session_row is None:
        session_row = ChatSession(id=session_id, namespace=namespace, character_id=character_id, source="main")
        db.add(session_row)

    db.query(ChatMessage).filter(ChatMessage.chat_id == session_id).delete(synchronize_session=False)

    for turn, msg in enumerate(request.messages):
        role = _safe_str(msg.get("role"), "assistant")
        row = ChatMessage(
            chat_id=session_id,
            turn=turn,
            role=role,
            speaker_name=_safe_str(msg.get("name"), ""),
            content=_safe_str(msg.get("content"), ""),
            reasoning=_safe_str(msg.get("reasoning"), "") or None,
            meta={"raw": msg},
        )
        db.add(row)

    db.commit()
    return ChatBulkResponse(messages=request.messages)


@router.delete("/chat/{character_id}")
def delete_chat_messages(
    character_id: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除某角色主会话。"""
    namespace = resolve_namespace(x_rph_user)
    session_id = f"{character_id}:main"

    db.query(ChatMessage).filter(ChatMessage.chat_id == session_id).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.namespace == namespace).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True}


@router.get("/memories/{character_id}", response_model=MemoryBulkResponse)
def get_memories(
    character_id: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取某角色记忆列表。"""
    namespace = resolve_namespace(x_rph_user)
    rows = (
        db.query(MemoryRecord)
        .filter(MemoryRecord.namespace == namespace, MemoryRecord.character_id == character_id)
        .order_by(MemoryRecord.turn.asc(), MemoryRecord.created_at.asc())
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        ts = 0
        if row.created_at:
            if row.created_at.tzinfo is None:
                ts = int(row.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            else:
                ts = int(row.created_at.timestamp() * 1000)
        item = {
            "id": row.id,
            "timestamp": ts,
            "turn": row.turn,
            "category": row.category,
            "summary": row.summary,
            "time": row.time_label or "",
            "location": row.location_label or "",
            "npcs": row.npcs or [],
            "depth": row.depth,
            "enabled": row.enabled,
        }
        if row.meta and isinstance(row.meta, dict):
            raw = row.meta.get("raw")
            if isinstance(raw, dict):
                item = raw
                if not item.get("id"):
                    item["id"] = row.id
        items.append(item)

    return MemoryBulkResponse(items=items)


@router.put("/memories/{character_id}", response_model=MemoryBulkResponse)
def put_memories(
    character_id: str,
    request: MemoryBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量替换某角色记忆列表。"""
    namespace = resolve_namespace(x_rph_user)

    db.query(MemoryRecord).filter(MemoryRecord.namespace == namespace, MemoryRecord.character_id == character_id).delete(
        synchronize_session=False
    )

    normalized: List[Dict[str, Any]] = []
    for item in request.items:
        memory_id = _safe_str(item.get("id"), "") or str(uuid.uuid4())
        normalized_item = dict(item)
        normalized_item["id"] = memory_id

        row = MemoryRecord(
            id=memory_id,
            namespace=namespace,
            character_id=character_id,
            turn=int(item.get("turn") or 0),
            category=_safe_str(item.get("category"), "event"),
            summary=_safe_str(item.get("summary"), ""),
            time_label=_safe_str(item.get("time"), "") or None,
            location_label=_safe_str(item.get("location"), "") or None,
            npcs=item.get("npcs") if isinstance(item.get("npcs"), list) else [],
            depth=int(item.get("depth") or 3),
            enabled=bool(item.get("enabled", True)),
            meta={"raw": normalized_item},
        )
        db.add(row)
        normalized.append(normalized_item)

    db.commit()
    return MemoryBulkResponse(items=normalized)


@router.delete("/memories/{character_id}")
def delete_memories(
    character_id: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除某角色的全部记忆。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(MemoryRecord).filter(MemoryRecord.namespace == namespace, MemoryRecord.character_id == character_id).delete(
        synchronize_session=False
    )
    db.commit()
    return {"deleted": True}
