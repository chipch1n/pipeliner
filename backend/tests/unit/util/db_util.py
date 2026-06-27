import os
from unittest.mock import MagicMock


def setup_mock_execute(mock_db, scalar_one_or_none_return_value):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=scalar_one_or_none_return_value)

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_db.execute = mock_execute