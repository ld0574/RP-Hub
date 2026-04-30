"""插件路由：插件配置管理与动作执行入口。"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PluginConfig
from ..plugin_runtime import invoke_plugin
from ..schemas import PluginCreateRequest, PluginInvokeRequest, PluginInvokeResponse, PluginResponse
from .storage import resolve_namespace

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _to_response(row: PluginConfig) -> PluginResponse:
    """ORM -> API 响应对象转换。"""
    return PluginResponse(
        id=row.id,
        name=row.name,
        type=row.type,
        description=row.description,
        enabled=row.enabled,
        config=row.config or {},
    )


@router.get("", response_model=List[PluginResponse])
def list_plugins(
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """列出当前命名空间下的全部插件。"""
    namespace = resolve_namespace(x_rph_user)
    rows = db.query(PluginConfig).filter(PluginConfig.namespace == namespace).order_by(PluginConfig.created_at.asc()).all()
    return [_to_response(row) for row in rows]


@router.post("", response_model=PluginResponse)
def create_plugin(
    request: PluginCreateRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """创建插件。"""
    namespace = resolve_namespace(x_rph_user)
    row = PluginConfig(
        namespace=namespace,
        name=request.name,
        type=request.type,
        description=request.description,
        enabled=request.enabled,
        config=request.config,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.delete("/{plugin_id}")
def delete_plugin(
    plugin_id: str,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """删除插件。"""
    namespace = resolve_namespace(x_rph_user)
    affected = db.query(PluginConfig).filter(PluginConfig.id == plugin_id, PluginConfig.namespace == namespace).delete()
    db.commit()
    if affected == 0:
        raise HTTPException(status_code=404, detail="插件不存在")
    return {"ok": True}


@router.post("/{plugin_id}/invoke", response_model=PluginInvokeResponse)
async def invoke_plugin_api(
    plugin_id: str,
    request: PluginInvokeRequest,
    db: Session = Depends(get_db),
    x_rph_user: Optional[str] = Header(default=None),
):
    """执行插件动作。"""
    namespace = resolve_namespace(x_rph_user)
    row = (
        db.query(PluginConfig)
        .filter(
            PluginConfig.id == plugin_id,
            PluginConfig.namespace == namespace,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="插件不存在")
    if not row.enabled:
        raise HTTPException(status_code=400, detail="插件已禁用")

    try:
        output = await invoke_plugin(row.type, row.config or {}, request.action, request.params or {})
        return PluginInvokeResponse(ok=True, output=output)
    except Exception as exc:  # noqa: BLE001
        return PluginInvokeResponse(ok=False, output={}, error=str(exc))
