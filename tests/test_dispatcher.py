import pytest
from unittest.mock import AsyncMock
from core.dispatcher import ToolDispatcher
from schemas.api_models import CommandResponse

@pytest.mark.asyncio
async def test_dispatcher_valid_action():
    mock_service = AsyncMock()
    mock_service.some_action.return_value = CommandResponse(success=True, message="OK")
    
    dispatcher = ToolDispatcher(mock_service)
    result = await dispatcher.dispatch("some_action", {"param": "value"})
    
    assert result.success is True
    mock_service.some_action.assert_awaited_once_with(param="value")