import pytest
from tool_adapter import invoke_tool

@pytest.mark.contract(parameters=["date", "store"], returns=["success", "synced_count", "errors"], permission="allowed")
def test_valid():
    result = invoke_tool("sync_inventory", {"date": "0229", "store": "us"}, ["inventory:write"])
    assert result["success"] is False
    assert type(result["synced_count"]) is int
    assert isinstance(result["errors"], list)

@pytest.mark.contract(parameters=["date", "store"])
@pytest.mark.parametrize("params,error", [
    ({"date": 123, "store": "us"}, TypeError),
    ({"date": "0101", "store": 123}, TypeError),
    ({"store": "us"}, ValueError),
    ({"date": "0101"}, ValueError),
    ({"date": "0101", "store": "xx"}, ValueError),
    ({"date": "1332", "store": "us"}, ValueError),
    ({"date": "101", "store": "us"}, ValueError),
])
def test_invalid(params, error):
    with pytest.raises(error):
        invoke_tool("sync_inventory", params, ["inventory:write"])

@pytest.mark.contract(permission="denied")
def test_permission_denied():
    with pytest.raises(PermissionError):
        invoke_tool("sync_inventory", {"date": "0101", "store": "us"}, [])
