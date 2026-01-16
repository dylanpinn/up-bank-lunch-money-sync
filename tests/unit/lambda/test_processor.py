import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Import the processor module
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../lambda/processor"))
from processor import convert_to_lunchmoney_format, process_transaction_event, sync_to_lunchmoney


class TestProcessorTransactionConversion:
    """Test transaction conversion from Up Bank format to Lunch Money format"""

    def test_convert_income_transaction_positive_amount(self):
        """
        Test that income transactions (positive amounts in Up Bank)
        result in positive amounts in Lunch Money
        """
        up_transaction = {
            "id": "txn-123",
            "attributes": {
                "amount": {"value": "50.00", "currencyCode": "AUD"},
                "description": "Salary deposit",
                "message": "Monthly salary",
                "createdAt": "2025-12-10T10:00:00Z",
                "settledAt": "2025-12-10T10:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Income should be positive
        assert result["amount"] == "50.0"
        assert float(result["amount"]) > 0

    def test_convert_expense_transaction_negative_amount(self):
        """
        Test that expense transactions (negative amounts in Up Bank)
        result in negative amounts in Lunch Money
        """
        up_transaction = {
            "id": "txn-456",
            "attributes": {
                "amount": {"value": "-25.50", "currencyCode": "AUD"},
                "description": "Coffee shop",
                "message": "Daily coffee",
                "createdAt": "2025-12-10T11:00:00Z",
                "settledAt": "2025-12-10T11:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Expense should be negative
        assert result["amount"] == "-25.5"
        assert float(result["amount"]) < 0

    def test_convert_zero_amount(self):
        """Test that zero amounts are handled correctly"""
        up_transaction = {
            "id": "txn-789",
            "attributes": {
                "amount": {"value": "0.00", "currencyCode": "AUD"},
                "description": "Transfer",
                "message": "",
                "createdAt": "2025-12-10T12:00:00Z",
                "settledAt": "2025-12-10T12:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Zero should be treated as zero
        assert result["amount"] == "0.0"

    def test_convert_preserves_decimal_places(self):
        """Test that decimal places are preserved correctly"""
        up_transaction = {
            "id": "txn-999",
            "attributes": {
                "amount": {"value": "123.45", "currencyCode": "AUD"},
                "description": "Payment",
                "message": "",
                "createdAt": "2025-12-10T13:00:00Z",
                "settledAt": "2025-12-10T13:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        assert float(result["amount"]) == 123.45

    def test_convert_large_negative_amount(self):
        """Test that large negative amounts (significant expenses) are handled"""
        up_transaction = {
            "id": "txn-large",
            "attributes": {
                "amount": {"value": "-1500.00", "currencyCode": "AUD"},
                "description": "Rent payment",
                "message": "Monthly rent",
                "createdAt": "2025-12-10T14:00:00Z",
                "settledAt": "2025-12-10T14:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Large expense should remain negative
        assert result["amount"] == "-1500.0"
        assert float(result["amount"]) < 0

    def test_convert_includes_required_fields(self):
        """Test that all required fields are included in the conversion"""
        up_transaction = {
            "id": "txn-complete",
            "attributes": {
                "amount": {"value": "100.00", "currencyCode": "AUD"},
                "description": "Shop purchase",
                "message": "Groceries",
                "createdAt": "2025-12-10T15:00:00Z",
                "settledAt": "2025-12-10T15:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Check all required fields are present
        assert "payee" in result
        assert "amount" in result
        assert "notes" in result
        assert "date" in result
        assert "external_id" in result
        assert "currency" in result
        assert "status" in result

    def test_convert_handles_string_amount(self):
        """Test that string amounts are correctly converted to float"""
        up_transaction = {
            "id": "txn-string",
            "attributes": {
                "amount": {"value": "-42.99", "currencyCode": "AUD"},
                "description": "Test",
                "message": "",
                "createdAt": "2025-12-10T16:00:00Z",
                "settledAt": "2025-12-10T16:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Should preserve negative sign
        assert float(result["amount"]) == -42.99


class TestLunchMoneySync:
    @patch("processor.requests.post")
    def test_sync_to_lunchmoney_applies_rules(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        sync_to_lunchmoney("test-api-key", {"external_id": "txn-1"})

        payload = mock_post.call_args.kwargs["json"]
        assert payload["debit_as_negative"] is True
        assert payload["apply_rules"] is True
        assert payload["check_for_recurring"] is True


class TestProcessorRoundUpHandling:
    """Test round-up transaction handling"""

    def test_convert_transaction_with_roundup_attribute(self):
        """
        Test that transactions with roundUp attribute
        return two separate transactions
        """
        up_transaction = {
            "id": "txn-with-roundup",
            "attributes": {
                "amount": {"value": "-24.50", "currencyCode": "AUD"},
                "description": "Coffee shop",
                "message": "",
                "createdAt": "2025-12-10T10:00:00Z",
                "settledAt": "2025-12-10T10:00:00Z",
                "roundUp": {
                    "amount": {"value": "-0.50", "currencyCode": "AUD"},
                    "boostPortion": None,
                },
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Should return a list of two transactions
        assert isinstance(result, list)
        assert len(result) == 2

        # First transaction is the main transaction
        main_txn = result[0]
        assert main_txn["amount"] == "-24.5"
        assert main_txn["payee"] == "Coffee shop"
        assert main_txn["external_id"] == "txn-with-roundup"

        # Second transaction is the round-up
        roundup_txn = result[1]
        assert roundup_txn["amount"] == "-0.5"
        assert roundup_txn["payee"] == "Round Up"
        assert roundup_txn["external_id"] == "txn-with-roundup-roundup"
        assert "Coffee shop" in roundup_txn["notes"]

    def test_convert_transaction_without_roundup(self):
        """
        Test that transactions without roundUp attribute
        return a single transaction
        """
        up_transaction = {
            "id": "txn-no-roundup",
            "attributes": {
                "amount": {"value": "-25.00", "currencyCode": "AUD"},
                "description": "Grocery store",
                "message": "",
                "createdAt": "2025-12-10T11:00:00Z",
                "settledAt": "2025-12-10T11:00:00Z",
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Should return a single transaction (not a list)
        assert isinstance(result, dict)
        assert result["amount"] == "-25.0"
        assert result["payee"] == "Grocery store"

    def test_convert_transaction_with_zero_roundup(self):
        """
        Test that transactions with zero roundUp amount
        only return the main transaction
        """
        up_transaction = {
            "id": "txn-zero-roundup",
            "attributes": {
                "amount": {"value": "-25.00", "currencyCode": "AUD"},
                "description": "Even amount",
                "message": "",
                "createdAt": "2025-12-10T12:00:00Z",
                "settledAt": "2025-12-10T12:00:00Z",
                "roundUp": {
                    "amount": {"value": "0.00", "currencyCode": "AUD"},
                    "boostPortion": None,
                },
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Should return only main transaction since roundup is zero
        assert isinstance(result, dict)
        assert result["amount"] == "-25.0"

    @patch("processor.get_secret")
    @patch("processor.fetch_up_transaction")
    @patch("processor.sync_to_lunchmoney")
    def test_process_transaction_event_with_roundup(
        self, mock_sync, mock_fetch, mock_get_secret
    ):
        """
        Test that transaction events with roundUp sync both transactions
        """
        # Set up environment variables
        os.environ["UP_API_KEY_ARN"] = "test-up-arn"
        os.environ["LUNCHMONEY_API_KEY_ARN"] = "test-lm-arn"

        # Mock secrets
        mock_get_secret.side_effect = ["test-up-key", "test-lm-key"]

        # Transaction with round-up
        transaction = {
            "id": "txn-main",
            "attributes": {
                "amount": {"value": "-24.50", "currencyCode": "AUD"},
                "description": "Coffee shop",
                "message": "",
                "createdAt": "2025-12-10T10:00:00Z",
                "settledAt": "2025-12-10T10:00:00Z",
                "roundUp": {
                    "amount": {"value": "-0.50", "currencyCode": "AUD"},
                    "boostPortion": None,
                },
            },
            "relationships": {
                "account": {"data": {}},
                "category": {"data": {}},
            },
        }

        mock_fetch.return_value = transaction

        # Webhook data
        webhook_data = {
            "data": {
                "attributes": {"eventType": "TRANSACTION_CREATED"},
                "relationships": {
                    "transaction": {"data": {"type": "transactions", "id": "txn-main"}}
                },
            }
        }

        # Process the transaction
        process_transaction_event(webhook_data)

        # Verify transaction was fetched once
        assert mock_fetch.call_count == 1

        # Verify both transactions were synced (main + roundup)
        assert mock_sync.call_count == 2

    def test_convert_real_up_bank_response_with_roundup(self):
        """
        Test with actual Up Bank API response structure
        """
        up_transaction = {
            "id": "0aad0b59-3f24-4a25-aeff-6bbd2c54d6ea",
            "attributes": {
                "status": "SETTLED",
                "rawText": "WARUNG BEBEK, UBUD INDONES",
                "description": "Warung Bebek Bengil",
                "message": None,
                "isCategorizable": True,
                "holdInfo": {
                    "amount": {
                        "currencyCode": "AUD",
                        "value": "-107.92",
                        "valueInBaseUnits": -10792,
                    },
                    "foreignAmount": None,
                },
                "roundUp": {
                    "amount": {
                        "currencyCode": "AUD",
                        "value": "-0.08",
                        "valueInBaseUnits": -8,
                    },
                    "boostPortion": None,
                },
                "cashback": None,
                "amount": {
                    "currencyCode": "AUD",
                    "value": "-107.92",
                    "valueInBaseUnits": -10792,
                },
                "foreignAmount": {
                    "currencyCode": "IDR",
                    "value": "-1053698.77",
                    "valueInBaseUnits": -105369877,
                },
                "cardPurchaseMethod": {
                    "method": "CARD_ON_FILE",
                    "cardNumberSuffix": "0001",
                },
                "settledAt": "2025-12-02T04:00:00+11:00",
                "createdAt": "2025-12-02T04:00:00+11:00",
            },
            "relationships": {
                "account": {"data": {"type": "accounts", "id": "44e39b44-4572-4379-b9e2-94f38e64d7c8"}},
                "category": {"data": None},
            },
        }

        result = convert_to_lunchmoney_format(up_transaction)

        # Should return a list of two transactions
        assert isinstance(result, list)
        assert len(result) == 2

        # First transaction is the main transaction
        main_txn = result[0]
        assert main_txn["amount"] == "-107.92"
        assert main_txn["payee"] == "Warung Bebek Bengil"
        assert main_txn["external_id"] == "0aad0b59-3f24-4a25-aeff-6bbd2c54d6ea"
        assert main_txn["currency"] == "aud"
        assert main_txn["date"] == "2025-12-02"

        # Second transaction is the round-up
        roundup_txn = result[1]
        assert roundup_txn["amount"] == "-0.08"
        assert roundup_txn["payee"] == "Round Up"
        assert roundup_txn["external_id"] == "0aad0b59-3f24-4a25-aeff-6bbd2c54d6ea-roundup"
        assert roundup_txn["currency"] == "aud"
        assert "Warung Bebek Bengil" in roundup_txn["notes"]


