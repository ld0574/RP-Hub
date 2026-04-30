"""主存储路由：提供前端状态的键值读写删除接口。"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AppKV
from ..schemas import StorageDeleteResponse, StorageGetResponse, StorageSetRequest

router = APIRouter(prefix="/api/storage", tags=["storage"])


def resolve_namespace(x_rph_user: Optional[str]) -> str:
    """将请求头映射为命名空间；为空时使用 default。"""
    namespace = (x_rph_user or "").strip()
    return namespace if namespace else "default"


@router.put("/{key}", response_model=StorageGetResponse)
def put_storage(
    key: str,
    request: StorageSetRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """写入或覆盖键值。"""
    namespace = resolve_namespace(x_rph_user)
    row = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == key).one_or_none()
    if row is None:
        row = AppKV(namespace=namespace, key=key, value=request.value)
        db.add(row)
    else:
        row.value = request.value
    db.commit()
    return StorageGetResponse(found=True, value=row.value)


@router.get("/{key}", response_model=StorageGetResponse)
def get_storage(
    key: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """读取键值。"""
    namespace = resolve_namespace(x_rph_user)
    row = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == key).one_or_none()
    if row is None:
        return StorageGetResponse(found=False, value=None)
    return StorageGetResponse(found=True, value=row.value)


@router.delete("/{key}", response_model=StorageDeleteResponse)
def delete_storage(
    key: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除键值。"""
    namespace = resolve_namespace(x_rph_user)
    affected = db.query(AppKV).filter(AppKV.namespace == namespace, AppKV.key == key).delete()
    db.commit()
    return StorageDeleteResponse(deleted=affected > 0)
