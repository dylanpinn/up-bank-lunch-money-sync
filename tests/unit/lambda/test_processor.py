import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Import the processor module
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../lambda/processor"))
from processor import convert_to_lunchmoney_format


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
                "amount": {"value": "50.00", "currency": "aud"},
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
                "amount": {"value": "-25.50", "currency": "aud"},
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
                "amount": {"value": "0.00", "currency": "aud"},
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
                "amount": {"value": "123.45", "currency": "aud"},
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
                "amount": {"value": "-1500.00", "currency": "aud"},
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
                "amount": {"value": "100.00", "currency": "aud"},
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
                "amount": {"value": "-42.99", "currency": "aud"},
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
