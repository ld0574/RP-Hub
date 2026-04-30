"""领域数据路由：角色/聊天/记忆的规范化表读写接口。"""

import uuid
from datetime import timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AppKV,
    Character,
    ChatMessage,
    ChatSession,
    MemoryRecord,
    PresetRecord,
    RegexRecord,
    WorldInfoRecord,
)
from ..schemas import (
    CharacterBulkRequest,
    CharacterBulkResponse,
    ChatBulkRequest,
    ChatBulkResponse,
    MemoryBulkRequest,
    MemoryBulkResponse,
    PresetBulkRequest,
    PresetBulkResponse,
    RegexBulkRequest,
    RegexBulkResponse,
    WorldInfoBulkRequest,
    WorldInfoBulkResponse,
)
from .storage import resolve_namespace

router = APIRouter(prefix="/api/domain", tags=["domain"])


def _safe_str(value: Any, default: str = "") -> str:
    """将任意值转成字符串，避免 `None` 或复杂对象导致入库异常。"""
    if value is None:
        return default
    return str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    """安全整数转换。"""
    try:
        return int(value)
    except Exception:
        return default


def _safe_list(value: Any, default: Optional[List[Any]] = None) -> List[Any]:
    """安全列表转换。"""
    if isinstance(value, list):
        return value
    return default[:] if default is not None else []


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

    # 兼容迁移：若规范化表为空，回读旧 app_kv 数据，避免前端出现“空角色”。
    if not items:
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == "silly_tavern_characters").one_or_none()
        if kv and isinstance(kv.value, list):
            return CharacterBulkResponse(items=kv.value)

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

    if not messages:
        kv_key = f"silly_tavern_chat_{character_id}"
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == kv_key).one_or_none()
        if kv and isinstance(kv.value, list):
            return ChatBulkResponse(messages=kv.value)

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

    if not items:
        kv_key = f"silly_tavern_memories_{character_id}"
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == kv_key).one_or_none()
        if kv and isinstance(kv.value, list):
            return MemoryBulkResponse(items=kv.value)

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


@router.get("/presets", response_model=PresetBulkResponse)
def get_presets(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取预设列表。"""
    namespace = resolve_namespace(x_rph_user)
    rows = (
        db.query(PresetRecord)
        .filter(PresetRecord.namespace == namespace)
        .order_by(PresetRecord.order_no.asc(), PresetRecord.created_at.asc())
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.meta or {}).get("raw") if isinstance(row.meta, dict) else None
        if isinstance(raw, dict):
            items.append(raw)
            continue
        items.append(
            {
                "id": row.id,
                "name": row.name,
                "content": row.content,
                "enabled": row.enabled,
                "order": row.order_no,
            }
        )

    if not items:
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == "silly_tavern_presets").one_or_none()
        if kv and isinstance(kv.value, list):
            return PresetBulkResponse(items=kv.value)

    return PresetBulkResponse(items=items)


@router.put("/presets", response_model=PresetBulkResponse)
def put_presets(
    request: PresetBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量替换预设列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(PresetRecord).filter(PresetRecord.namespace == namespace).delete(synchronize_session=False)

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(request.items):
        item_id = _safe_str(item.get("id"), "") or str(uuid.uuid4())
        normalized_item = dict(item)
        normalized_item["id"] = item_id
        row = PresetRecord(
            id=item_id,
            namespace=namespace,
            name=_safe_str(item.get("name"), f"Preset {idx + 1}"),
            content=_safe_str(item.get("content"), ""),
            enabled=bool(item.get("enabled", True)),
            order_no=_safe_int(item.get("order"), idx),
            meta={"raw": normalized_item},
        )
        db.add(row)
        normalized.append(normalized_item)

    db.commit()
    return PresetBulkResponse(items=normalized)


@router.delete("/presets")
def delete_presets(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除预设列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(PresetRecord).filter(PresetRecord.namespace == namespace).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True}


@router.get("/regex", response_model=RegexBulkResponse)
def get_regex_records(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取正则脚本列表。"""
    namespace = resolve_namespace(x_rph_user)
    rows = (
        db.query(RegexRecord)
        .filter(RegexRecord.namespace == namespace)
        .order_by(RegexRecord.order_no.asc(), RegexRecord.created_at.asc())
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.meta or {}).get("raw") if isinstance(row.meta, dict) else None
        if isinstance(raw, dict):
            items.append(raw)
            continue
        items.append(
            {
                "id": row.id,
                "name": row.name,
                "regex": row.regex,
                "flags": row.flags or "",
                "replacement": row.replacement or "",
                "placement": row.placement or [1, 2],
                "markdownOnly": row.markdown_only,
                "promptOnly": row.prompt_only,
                "enabled": row.enabled,
                "order": row.order_no,
            }
        )

    if not items:
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == "silly_tavern_regex").one_or_none()
        if kv and isinstance(kv.value, list):
            return RegexBulkResponse(items=kv.value)

    return RegexBulkResponse(items=items)


@router.put("/regex", response_model=RegexBulkResponse)
def put_regex_records(
    request: RegexBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量替换正则脚本列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(RegexRecord).filter(RegexRecord.namespace == namespace).delete(synchronize_session=False)

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(request.items):
        item_id = _safe_str(item.get("id"), "") or str(uuid.uuid4())
        normalized_item = dict(item)
        normalized_item["id"] = item_id

        row = RegexRecord(
            id=item_id,
            namespace=namespace,
            name=_safe_str(item.get("name"), f"Regex {idx + 1}"),
            regex=_safe_str(item.get("regex"), ""),
            flags=_safe_str(item.get("flags"), ""),
            replacement=_safe_str(item.get("replacement"), ""),
            placement=_safe_list(item.get("placement"), [1, 2]),
            markdown_only=bool(item.get("markdownOnly", item.get("markdown_only", False))),
            prompt_only=bool(item.get("promptOnly", item.get("prompt_only", False))),
            enabled=bool(item.get("enabled", True)),
            order_no=_safe_int(item.get("order"), idx),
            meta={"raw": normalized_item},
        )
        db.add(row)
        normalized.append(normalized_item)

    db.commit()
    return RegexBulkResponse(items=normalized)


@router.delete("/regex")
def delete_regex_records(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除正则脚本列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(RegexRecord).filter(RegexRecord.namespace == namespace).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True}


@router.get("/worldinfo", response_model=WorldInfoBulkResponse)
def get_worldinfo_records(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取世界书条目列表。"""
    namespace = resolve_namespace(x_rph_user)
    rows = (
        db.query(WorldInfoRecord)
        .filter(WorldInfoRecord.namespace == namespace)
        .order_by(WorldInfoRecord.order_no.asc(), WorldInfoRecord.created_at.asc())
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = dict(row.meta or {}).get("raw") if isinstance(row.meta, dict) else None
        if isinstance(raw, dict):
            items.append(raw)
            continue
        items.append(
            {
                "id": row.id,
                "comment": row.name,
                "content": row.content,
                "position": row.position,
                "depth": row.depth,
                "order": row.order_no,
                "enabled": row.enabled,
                "keys": row.keys or [],
                "secondary_keys": row.secondary_keys or [],
            }
        )

    if not items:
        kv = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == "silly_tavern_worldinfo").one_or_none()
        if kv and isinstance(kv.value, list):
            return WorldInfoBulkResponse(items=kv.value)

    return WorldInfoBulkResponse(items=items)


@router.put("/worldinfo", response_model=WorldInfoBulkResponse)
def put_worldinfo_records(
    request: WorldInfoBulkRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """全量替换世界书条目列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(WorldInfoRecord).filter(WorldInfoRecord.namespace == namespace).delete(synchronize_session=False)

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(request.items):
        item_id = _safe_str(item.get("id"), "") or str(uuid.uuid4())
        normalized_item = dict(item)
        normalized_item["id"] = item_id

        row = WorldInfoRecord(
            id=item_id,
            namespace=namespace,
            character_id=_safe_str(item.get("character_id"), "") or None,
            name=_safe_str(item.get("comment"), _safe_str(item.get("name"), f"WorldInfo {idx + 1}")),
            content=_safe_str(item.get("content"), ""),
            position=_safe_str(item.get("position"), "at_depth"),
            depth=_safe_int(item.get("depth"), 4),
            order_no=_safe_int(item.get("order"), idx),
            enabled=bool(item.get("enabled", True)),
            keys=_safe_list(item.get("keys")),
            secondary_keys=_safe_list(item.get("secondary_keys", item.get("secondaryKeys"))),
            meta={"raw": normalized_item},
        )
        db.add(row)
        normalized.append(normalized_item)

    db.commit()
    return WorldInfoBulkResponse(items=normalized)


@router.delete("/worldinfo")
def delete_worldinfo_records(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除世界书条目列表。"""
    namespace = resolve_namespace(x_rph_user)
    db.query(WorldInfoRecord).filter(WorldInfoRecord.namespace == namespace).delete(synchronize_session=False)
    db.commit()
    return {"deleted": True}
