"""插件运行时调度器：根据插件类型分发到 HTTP 或 Bluetooth 执行器。"""

from typing import Any, Dict

from .plugins.bluetooth_executor import run_bluetooth_action
from .plugins.http_executor import run_http_action


async def invoke_plugin(plugin_type: str, config: Dict[str, Any], action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """统一插件调用入口。"""
    if plugin_type == "http":
        return await run_http_action(config, action, params)

    if plugin_type == "bluetooth":
        return await run_bluetooth_action(config, action, params)

    raise ValueError(f"不支持的插件类型: {plugin_type}")
