"""Deliberate real implementation defect, not a mocked return in a test."""
from tool_adapter import demo_inventory


def sync_inventory(parameters, permissions):
    demo_inventory("sync_inventory", parameters, permissions)
    return {"success": True, "synced_count": "10", "errors": []}
