"""HTTP 插件执行器：用于调用外部玩具/设备网关 HTTP API。"""

from typing import Any, Dict

import httpx


async def run_http_action(config: Dict[str, Any], action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """执行 HTTP 插件动作。

    约定：
    - action 目前仅支持 request。
    - config 可包含 base_url/default_headers/timeout。
    - params 支持 method/path/headers/query/body。
    """
    if action != "request":
        raise ValueError(f"HTTP 插件不支持动作: {action}")

    base_url = str(config.get("base_url", "")).rstrip("/")
    path = str(params.get("path", "")).lstrip("/")
    method = str(params.get("method", "POST")).upper()
    timeout = float(config.get("timeout", 15))

    if not base_url:
        raise ValueError("HTTP 插件缺少 base_url 配置")

    url = f"{base_url}/{path}" if path else base_url

    default_headers = config.get("default_headers") or {}
    req_headers = params.get("headers") or {}
    merged_headers = {**default_headers, **req_headers}

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=merged_headers,
            params=params.get("query") or None,
            json=params.get("body") if "body" in params else None,
        )

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        payload: Any = response.json()
    else:
        payload = response.text

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "data": payload,
    }
