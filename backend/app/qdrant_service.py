"""Qdrant 服务封装：负责记忆向量写入与检索。"""

import uuid
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .config import get_settings

settings = get_settings()


class QdrantMemoryService:
    """记忆向量服务。

    说明：
    - 向量主存放在 Qdrant。
    - 通过 namespace + character_uuid 过滤，实现用户与角色隔离。
    """

    def __init__(self) -> None:
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
            timeout=10.0,
        )
        self.collection = settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """确保集合存在；不存在时按配置创建。"""
        try:
            self.client.get_collection(self.collection)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=settings.embedding_dim, distance=qm.Distance.COSINE),
            )

    @staticmethod
    def _point_id(namespace: str, memory_id: str) -> str:
        """将任意 memory_id 映射为稳定 UUID，便于幂等更新。"""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"rphub:{namespace}:{memory_id}"))

    def upsert_memory(
        self,
        *,
        namespace: str,
        memory_id: str,
        character_uuid: str,
        category: str,
        turn: int,
        summary: str,
        embedding: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """写入或更新单条记忆向量。"""
        merged_payload = {
            "namespace": namespace,
            "memory_id": memory_id,
            "character_uuid": character_uuid,
            "category": category,
            "turn": turn,
            "summary": summary,
            **(payload or {}),
        }

        self.client.upsert(
            collection_name=self.collection,
            points=[
                qm.PointStruct(
                    id=self._point_id(namespace, memory_id),
                    vector=embedding,
                    payload=merged_payload,
                )
            ],
            wait=False,
        )

    def search_memory(
        self,
        *,
        namespace: str,
        character_uuid: str,
        embedding: List[float],
        limit: int,
        score_threshold: float,
    ) -> List[Dict[str, Any]]:
        """按向量相似度检索角色记忆。"""
        hits = self.client.search(
            collection_name=self.collection,
            query_vector=embedding,
            query_filter=qm.Filter(
                must=[
                    qm.FieldCondition(key="namespace", match=qm.MatchValue(value=namespace)),
                    qm.FieldCondition(key="character_uuid", match=qm.MatchValue(value=character_uuid)),
                ]
            ),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            with_vectors=False,
        )

        results: List[Dict[str, Any]] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                {
                    "memory_id": payload.get("memory_id", ""),
                    "score": float(hit.score),
                    "category": payload.get("category", "event"),
                    "turn": int(payload.get("turn", 0) or 0),
                    "summary": payload.get("summary", ""),
                    "payload": payload,
                }
            )
        return results
