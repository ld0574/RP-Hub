"""记忆向量路由：写入与检索 Qdrant 记忆，并同步元信息到数据库。"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MemoryVectorMeta
from ..qdrant_service import QdrantMemoryService
from ..schemas import MemorySearchItem, MemorySearchRequest, MemorySearchResponse, MemoryUpsertRequest
from .storage import resolve_namespace

router = APIRouter(prefix="/api/memory", tags=["memory"])

_qdrant_service: Optional[QdrantMemoryService] = None


def get_qdrant_service() -> QdrantMemoryService:
    """懒加载 Qdrant 客户端，降低启动阶段失败概率。"""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantMemoryService()
    return _qdrant_service


@router.post("/upsert")
def upsert_memory(
    request: MemoryUpsertRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """写入单条记忆向量。"""
    namespace = resolve_namespace(x_rph_user)

    try:
        service = get_qdrant_service()
        service.upsert_memory(
            namespace=namespace,
            memory_id=request.memory_id,
            character_uuid=request.character_uuid,
            category=request.category,
            turn=request.turn,
            summary=request.summary,
            embedding=request.embedding,
            payload=request.payload,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Qdrant 写入失败: {exc}") from exc

    meta = (
        db.query(MemoryVectorMeta)
        .filter(
            MemoryVectorMeta.id == request.memory_id,
            MemoryVectorMeta.namespace == namespace,
        )
        .one_or_none()
    )
    if meta is None:
        meta = MemoryVectorMeta(
            id=request.memory_id,
            namespace=namespace,
            character_uuid=request.character_uuid,
            category=request.category,
            turn=request.turn,
            summary=request.summary,
            payload=request.payload,
        )
        db.add(meta)
    else:
        meta.character_uuid = request.character_uuid
        meta.category = request.category
        meta.turn = request.turn
        meta.summary = request.summary
        meta.payload = request.payload

    db.commit()
    return {"ok": True}


@router.post("/search", response_model=MemorySearchResponse)
def search_memory(
    request: MemorySearchRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """按 embedding 检索角色记忆。"""
    namespace = resolve_namespace(x_rph_user)

    try:
        service = get_qdrant_service()
        hits = service.search_memory(
            namespace=namespace,
            character_uuid=request.character_uuid,
            embedding=request.embedding,
            limit=request.limit,
            score_threshold=request.score_threshold,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"Qdrant 检索失败: {exc}") from exc

    items = []
    for hit in hits:
        memory_id = hit.get("memory_id")
        summary = hit.get("summary") or ""
        category = hit.get("category") or "event"
        turn = int(hit.get("turn") or 0)
        payload = hit.get("payload") or {}

        if memory_id:
            meta = (
                db.query(MemoryVectorMeta)
                .filter(
                    MemoryVectorMeta.id == memory_id,
                    MemoryVectorMeta.namespace == namespace,
                )
                .one_or_none()
            )
            if meta is not None:
                summary = meta.summary
                category = meta.category
                turn = meta.turn
                payload = meta.payload or payload

        items.append(
            MemorySearchItem(
                memory_id=memory_id or "",
                score=float(hit.get("score") or 0.0),
                category=category,
                turn=turn,
                summary=summary,
                payload=payload,
            )
        )

    return MemorySearchResponse(items=items)
