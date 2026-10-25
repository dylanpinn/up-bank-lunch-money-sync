import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../lambda/account_sync")
)


class TestFetchUpAccountsFiltering:
    """Test that fetch_up_accounts applies ownershipType filter correctly."""

    @patch.dict(os.environ, {"SYNC_OWNERSHIP_TYPES": ""}, clear=False)
    def test_no_filter_when_env_var_empty(self):
        """When SYNC_OWNERSHIP_TYPES is empty, no filter param is added."""
        import account_sync

        importlib.reload(account_sync)

        with patch("account_sync.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [], "links": {"next": None}}
            mock_get.return_value = mock_response

            account_sync.fetch_up_accounts("test-api-key")

            called_url = mock_get.call_args[0][0]
            assert "filter[ownershipType]" not in called_url
            assert called_url == "https://api.up.com.au/api/v1/accounts"

    @patch.dict(os.environ, {"SYNC_OWNERSHIP_TYPES": "JOINT"}, clear=False)
    def test_filter_applied_when_env_var_set(self):
        """When SYNC_OWNERSHIP_TYPES=JOINT, filter param is added."""
        import account_sync

        importlib.reload(account_sync)

        with patch("account_sync.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [], "links": {"next": None}}
            mock_get.return_value = mock_response

            account_sync.fetch_up_accounts("test-api-key")

            called_url = mock_get.call_args[0][0]
            assert "filter[ownershipType]=JOINT" in called_url

    @patch.dict(
        os.environ, {"SYNC_OWNERSHIP_TYPES": "JOINT,INDIVIDUAL"}, clear=False
    )
    def test_multiple_ownership_types(self):
        """When multiple types are configured, all are included in filter."""
        import account_sync

        importlib.reload(account_sync)

        with patch("account_sync.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [], "links": {"next": None}}
            mock_get.return_value = mock_response

            account_sync.fetch_up_accounts("test-api-key")

            called_url = mock_get.call_args[0][0]
            # Sorted, so INDIVIDUAL comes before JOINT
            assert "filter[ownershipType]=INDIVIDUAL,JOINT" in called_url
