import pytest
from tool_adapter import invoke_tool


@pytest.mark.contract(
    parameters=["date", "store"],
    returns=["success", "synced_count", "errors"],
    permission="allowed",
)
def test_sync_inventory_valid_parameters_returns_expected_fields():
    result = invoke_tool(
        "sync_inventory",
        {"date": "0229", "store": "us"},
        ["inventory:write"],
    )

    assert isinstance(result, dict)
    assert "success" in result
    assert isinstance(result["success"], bool)
    assert "synced_count" in result
    assert isinstance(result["synced_count"], int)
    assert not isinstance(result["synced_count"], bool)
    assert "errors" in result
    assert isinstance(result["errors"], list)


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_date_type_error():
    with pytest.raises(TypeError):
        invoke_tool(
            "sync_inventory",
            {"date": 229, "store": "us"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_store_type_error():
    with pytest.raises(TypeError):
        invoke_tool(
            "sync_inventory",
            {"date": "0229", "store": 1},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_missing_date_required():
    with pytest.raises(ValueError):
        invoke_tool(
            "sync_inventory",
            {"store": "us"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_missing_store_required():
    with pytest.raises(ValueError):
        invoke_tool(
            "sync_inventory",
            {"date": "0229"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_store_enum_out_of_range():
    with pytest.raises(ValueError):
        invoke_tool(
            "sync_inventory",
            {"date": "0229", "store": "xx"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_date_format_non_ascii_digits():
    with pytest.raises(ValueError):
        invoke_tool(
            "sync_inventory",
            {"date": "02AA", "store": "us"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="allowed")
def test_sync_inventory_date_format_invalid_calendar_date():
    with pytest.raises(ValueError):
        invoke_tool(
            "sync_inventory",
            {"date": "0230", "store": "us"},
            ["inventory:write"],
        )


@pytest.mark.contract(parameters=["date", "store"], permission="denied")
def test_sync_inventory_without_permission_raises_permission_error():
    with pytest.raises(PermissionError):
        invoke_tool(
            "sync_inventory",
            {"date": "0229", "store": "us"},
            [],
        )
