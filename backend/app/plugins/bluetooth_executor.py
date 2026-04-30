"""Bluetooth 插件执行器：支持蓝牙扫描与 GATT 写入（依赖 bleak）。"""

from typing import Any, Dict, List


def _safe_import_bleak():
    """延迟导入 bleak，避免在无蓝牙环境下启动失败。"""
    try:
        from bleak import BleakClient, BleakScanner  # type: ignore

        return BleakClient, BleakScanner
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"蓝牙运行环境不可用: {exc}") from exc


async def run_bluetooth_action(config: Dict[str, Any], action: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """执行蓝牙插件动作。

    支持动作：
    - scan: 扫描附近设备
    - write_gatt: 连接后向指定特征写入字节
    """
    BleakClient, BleakScanner = _safe_import_bleak()

    if action == "scan":
        timeout = float(params.get("timeout", config.get("scan_timeout", 5)))
        devices = await BleakScanner.discover(timeout=timeout)
        output: List[Dict[str, Any]] = []
        for d in devices:
            output.append({
                "name": d.name,
                "address": d.address,
                "rssi": getattr(d, "rssi", None),
                "metadata": getattr(d, "metadata", None),
            })
        return {"devices": output}

    if action == "write_gatt":
        address = str(params.get("address") or config.get("address") or "").strip()
        char_uuid = str(params.get("characteristic") or "").strip()
        payload = params.get("payload")

        if not address:
            raise ValueError("write_gatt 缺少 address")
        if not char_uuid:
            raise ValueError("write_gatt 缺少 characteristic")
        if payload is None:
            raise ValueError("write_gatt 缺少 payload")

        if isinstance(payload, list):
            data = bytes(int(x) & 0xFF for x in payload)
        elif isinstance(payload, str):
            encoding = str(params.get("encoding", "utf-8")).lower()
            if encoding == "hex":
                data = bytes.fromhex(payload)
            else:
                data = payload.encode(encoding)
        else:
            raise ValueError("payload 仅支持字符串或数字数组")

        async with BleakClient(address) as client:
            await client.write_gatt_char(char_uuid, data, response=bool(params.get("response", False)))

        return {"address": address, "characteristic": char_uuid, "bytes_written": len(data)}

    raise ValueError(f"Bluetooth 插件不支持动作: {action}")
