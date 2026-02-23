"""Unit tests for DLQ redrive Lambda function."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add lambda/dlq_redrive to path for imports
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../../lambda/dlq_redrive")
)


@pytest.fixture
def dlq_redrive_env():
    """Set up environment variables for DLQ redrive tests."""
    os.environ["DLQ_URL"] = "https://sqs.us-east-1.amazonaws.com/123456789/test-dlq"
    os.environ["MAIN_QUEUE_URL"] = (
        "https://sqs.us-east-1.amazonaws.com/123456789/test-queue"
    )
    os.environ["MAX_MESSAGES"] = "10"
    yield
    # Cleanup
    os.environ.pop("DLQ_URL", None)
    os.environ.pop("MAIN_QUEUE_URL", None)
    os.environ.pop("MAX_MESSAGES", None)


@pytest.fixture
def mock_sqs():
    """Mock boto3 SQS client."""
    with patch("dlq_redrive.get_sqs_client") as mock_get_client:
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        yield mock_client


class TestDlqRedrive:
    """Test cases for DLQ redrive Lambda function."""

    def test_missing_environment_variables(self, mock_sqs):
        """Test handler fails gracefully when environment variables are missing."""
        from dlq_redrive import handler

        result = handler({}, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
        assert "environment variables" in body["error"].lower()

    def test_empty_dlq(self, dlq_redrive_env, mock_sqs):
        """Test handler when DLQ has no messages."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "0"}
        }

        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 0
        assert body["failedCount"] == 0
        assert "No messages" in body["message"]

    def test_successful_redrive_single_message(self, dlq_redrive_env, mock_sqs):
        """Test successful redrive of a single message."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "1"}
        }

        # First call returns message, second call returns empty
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-123",
                        "ReceiptHandle": "receipt-123",
                        "Body": json.dumps({"test": "data"}),
                    }
                ]
            },
            {"Messages": []},
        ]

        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 1
        assert body["failedCount"] == 0

        # Verify message was sent to main queue
        mock_sqs.send_message.assert_called_once()
        send_call = mock_sqs.send_message.call_args
        assert send_call[1]["QueueUrl"] == os.environ["MAIN_QUEUE_URL"]
        assert json.dumps({"test": "data"}) in send_call[1]["MessageBody"]

        # Verify message was deleted from DLQ
        mock_sqs.delete_message.assert_called_once_with(
            QueueUrl=os.environ["DLQ_URL"], ReceiptHandle="receipt-123"
        )

    def test_successful_redrive_multiple_messages(self, dlq_redrive_env, mock_sqs):
        """Test successful redrive of multiple messages."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "3"}
        }

        # First call returns 3 messages, second call returns empty
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(3)
                ]
            },
            {"Messages": []},
        ]

        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 3
        assert body["failedCount"] == 0

        # Verify all messages were sent and deleted
        assert mock_sqs.send_message.call_count == 3
        assert mock_sqs.delete_message.call_count == 3

    def test_redrive_with_message_attributes(self, dlq_redrive_env, mock_sqs):
        """Test redrive preserves message attributes."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "1"}
        }

        message_attributes = {
            "AttributeName": {"StringValue": "AttributeValue", "DataType": "String"}
        }

        mock_sqs.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-123",
                    "ReceiptHandle": "receipt-123",
                    "Body": json.dumps({"test": "data"}),
                    "MessageAttributes": message_attributes,
                }
            ]
        }

        result = handler({}, None)

        assert result["statusCode"] == 200

        # Verify message attributes were preserved
        send_call = mock_sqs.send_message.call_args
        assert "MessageAttributes" in send_call[1]
        assert send_call[1]["MessageAttributes"] == message_attributes

    def test_max_messages_limit(self, dlq_redrive_env, mock_sqs):
        """Test that max_messages parameter is respected."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "100"}
        }

        # Return more messages than max_messages
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(10)
                ]
            },
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(10, 20)
                ]
            },
        ]

        # Set max messages to 5 via event parameter
        result = handler({"maxMessages": 5}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 5
        assert body["failedCount"] == 0

    def test_partial_failure_during_redrive(self, dlq_redrive_env, mock_sqs):
        """Test that partial failures are handled correctly."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "3"}
        }

        # First call returns messages, second returns empty
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(3)
                ]
            },
            {"Messages": []},
        ]

        # Make second message fail
        def send_side_effect(*args, **kwargs):
            body = kwargs.get("MessageBody", "")
            if '"index": 1' in body:
                raise Exception("Send failed")

        mock_sqs.send_message.side_effect = send_side_effect

        result = handler({}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 2
        assert body["failedCount"] == 1
        assert "errors" in body

    def test_delete_only_after_successful_send(self, dlq_redrive_env, mock_sqs):
        """Test that messages are only deleted from DLQ after successful send."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "2"}
        }

        # First call returns messages, second returns empty
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": "msg-1",
                        "ReceiptHandle": "receipt-1",
                        "Body": json.dumps({"index": 1}),
                    },
                    {
                        "MessageId": "msg-2",
                        "ReceiptHandle": "receipt-2",
                        "Body": json.dumps({"index": 2}),
                    },
                ]
            },
            {"Messages": []},
        ]

        # First send succeeds, second fails
        mock_sqs.send_message.side_effect = [None, Exception("Send failed")]

        result = handler({}, None)

        # Only one message should be deleted (the successful one)
        assert mock_sqs.delete_message.call_count == 1
        delete_call = mock_sqs.delete_message.call_args
        assert delete_call[1]["ReceiptHandle"] == "receipt-1"

    def test_exception_during_receive(self, dlq_redrive_env, mock_sqs):
        """Test handling of exceptions during message receive."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "5"}
        }

        mock_sqs.receive_message.side_effect = Exception("SQS error")

        result = handler({}, None)

        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert "error" in body
        assert "SQS error" in body["error"]

    def test_custom_max_messages_from_event(self, dlq_redrive_env, mock_sqs):
        """Test that maxMessages from event overrides environment variable."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "50"}
        }

        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(10)
                ]
            },
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(10, 15)
                ]
            },
        ]

        # Pass maxMessages in event
        result = handler({"maxMessages": 15}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 15

    def test_no_more_messages_available(self, dlq_redrive_env, mock_sqs):
        """Test when DLQ empties during processing."""
        from dlq_redrive import handler

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {"ApproximateNumberOfMessages": "20"}
        }

        # First call returns messages, second returns empty (queue emptied)
        mock_sqs.receive_message.side_effect = [
            {
                "Messages": [
                    {
                        "MessageId": f"msg-{i}",
                        "ReceiptHandle": f"receipt-{i}",
                        "Body": json.dumps({"index": i}),
                    }
                    for i in range(5)
                ]
            },
            {"Messages": []},  # No more messages
        ]

        result = handler({"maxMessages": 20}, None)

        assert result["statusCode"] == 200
        body = json.loads(result["body"])
        assert body["redrivenCount"] == 5
        assert body["failedCount"] == 0
