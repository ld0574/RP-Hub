"""LLM 代理路由：用于解决浏览器直连第三方模型接口的 CORS 与方法差异问题。"""

import json
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/llm", tags=["llm-proxy"])


class LLMModelsRequest(BaseModel):
    """模型列表请求。"""

    api_url: str = Field(..., min_length=1)
    api_key: str = ""


class LLMChatRequest(BaseModel):
    """聊天补全代理请求。"""

    api_url: str = Field(..., min_length=1)
    api_key: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


def _normalize_openai_base_url(api_url: str) -> str:
    """规范化 OpenAI 兼容 base URL。

    兼容用户输入：
    - https://host/v1
    - https://host/v1/
    - https://host/v1/chat/completions
    - https://host/chat/completions
    """
    base = (api_url or "").strip().rstrip("/")
    strip_suffixes = (
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/models",
        "/models",
    )
    for suffix in strip_suffixes:
        if base.endswith(suffix):
            return base[: -len(suffix)]
    return base


def _build_endpoint(api_url: str, endpoint: str) -> str:
    """根据 base URL 构建指定 API endpoint。"""
    base = _normalize_openai_base_url(api_url)
    if not base:
        raise HTTPException(status_code=400, detail="api_url 为空")
    if endpoint.startswith("/"):
        endpoint = endpoint[1:]
    if base.endswith("/v1"):
        return f"{base}/{endpoint}"
    return f"{base}/v1/{endpoint}"


def _auth_headers(api_key: str) -> Dict[str, str]:
    """生成上游鉴权请求头。"""
    headers = {"Content-Type": "application/json"}
    if (api_key or "").strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    return headers


@router.post("/models")
async def proxy_models(request: LLMModelsRequest):
    """代理模型列表请求。

    特殊处理：若上游返回 405/404（部分兼容服务不开放 models），
    返回 200 + 空列表，避免前端硬报错。
    """
    url = _build_endpoint(request.api_url, "models")
    headers = _auth_headers(request.api_key)

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"上游连接失败: {exc}") from exc

    if response.status_code in (404, 405):
        return {"data": [], "warning": f"Upstream /models unavailable ({response.status_code})"}

    if not response.is_success:
        detail = response.text[:1000] if response.text else f"HTTP {response.status_code}"
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {
            "data": [],
            "warning": "Upstream /models returned non-JSON body",
        }


@router.post("/chat/completions")
async def proxy_chat_completions(request: LLMChatRequest):
    """代理聊天补全请求，支持流式转发。"""
    url = _build_endpoint(request.api_url, "chat/completions")
    headers = _auth_headers(request.api_key)
    payload = request.payload or {}
    is_stream = bool(payload.get("stream", False))

    if is_stream:

        async def stream_bytes():
            """将上游 SSE 字节流原样透传给前端。"""
            try:
                async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
                    async with client.stream("POST", url, headers=headers, json=payload) as upstream:
                        if not upstream.is_success:
                            error_text = (await upstream.aread()).decode("utf-8", errors="ignore").strip()
                            error_json = json.dumps(
                                {"error": error_text[:600] or f"HTTP {upstream.status_code}"},
                                ensure_ascii=False,
                            )
                            yield f"data: {error_json}\n\n".encode("utf-8")
                            return

                        async for chunk in upstream.aiter_raw():
                            if chunk:
                                yield chunk
            except Exception as exc:  # noqa: BLE001
                error_json = json.dumps({"error": f"上游连接失败: {exc}"}, ensure_ascii=False)
                yield f"data: {error_json}\n\n".encode("utf-8")

        return StreamingResponse(
            stream_bytes(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as upstream:
                if not upstream.is_success:
                    error_bytes = await upstream.aread()
                    error_text = error_bytes.decode("utf-8", errors="ignore").strip()
                    raise HTTPException(
                        status_code=upstream.status_code,
                        detail=error_text[:1000] or f"HTTP {upstream.status_code}",
                    )

                content_type_raw = upstream.headers.get("content-type") or ""
                content_type = content_type_raw.lower()

                # 兼容：部分上游即使 stream=false 也返回 SSE，并在 [DONE] 后保持连接，
                # 若等待其主动断开会导致前端体感延迟（常见约 60s）。这里在 [DONE] 提前收尾。
                if "text/event-stream" in content_type:
                    lines: list[str] = []
                    async for line in upstream.aiter_lines():
                        lines.append(line)
                        stripped = line.strip()
                        if stripped in ("data: [DONE]", "[DONE]"):
                            break

                    sse_text = "\n".join(lines)
                    return Response(
                        content=sse_text,
                        status_code=upstream.status_code,
                        headers={"Content-Type": "text/plain; charset=utf-8"},
                    )

                body_bytes = await upstream.aread()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"上游连接失败: {exc}") from exc

    if "application/json" in content_type:
        try:
            payload_json = json.loads(body_bytes)
            return JSONResponse(content=payload_json, status_code=upstream.status_code)
        except Exception:  # noqa: BLE001
            pass

    return Response(
        content=body_bytes,
        status_code=upstream.status_code,
        headers={"Content-Type": content_type_raw or "text/plain; charset=utf-8"},
    )
