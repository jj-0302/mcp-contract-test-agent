"""Local demonstration only; replace this adapter to test a real tool."""
from datetime import datetime
import os
import importlib.util
from pathlib import Path


def invoke_tool(tool_name, parameters, permissions):
    target = os.environ.get("MCP_TOOL_IMPLEMENTATION")
    if target:
        spec = importlib.util.spec_from_file_location("selected_tool", Path(target).resolve())
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.sync_inventory(parameters, permissions)
    return demo_inventory(tool_name, parameters, permissions)


def demo_inventory(tool_name, parameters, permissions):
    if tool_name != "sync_inventory":
        raise NotImplementedError("请为新工具实现 tool_adapter.invoke_tool")
    if "inventory:write" not in permissions:
        raise PermissionError("需要 inventory:write")
    for name in ("date", "store"):
        if name not in parameters:
            raise ValueError("缺少必填参数: " + name)
        if not isinstance(parameters[name], str):
            raise TypeError(name + " 必须是 string")
    date = parameters["date"]
    if len(date) != 4 or not date.isascii() or not date.isdigit():
        raise ValueError("date 必须是 MMDD")
    try:
        datetime.strptime("2000" + date, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("date 必须是有效 MMDD 日期") from exc
    if parameters["store"] not in ("us", "de", "ca", "uk", "fr", "jp", "au"):
        raise ValueError("store 不在枚举范围内")
    return {"success": True, "synced_count": 0, "errors": []}
