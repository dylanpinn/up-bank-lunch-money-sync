"""
DLQ Redrive Lambda Function

This function redrives (reprocesses) messages from the Dead Letter Queue (DLQ)
back to the main processing queue. It can be triggered manually or on a schedule.

Environment Variables:
    - DLQ_URL: URL of the Dead Letter Queue
    - MAIN_QUEUE_URL: URL of the main processing queue
    - MAX_MESSAGES: Maximum number of messages to redrive per invocation (default: 10)
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_sqs_client():
    """Get or create SQS client (lazy initialization for testing)."""
    return boto3.client("sqs")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for redriving messages from DLQ to main queue.

    Args:
        event: Lambda event object (can contain 'maxMessages' parameter)
        context: Lambda context object

    Returns:
        Response with number of messages redriven and any errors
    """
    dlq_url = os.environ.get("DLQ_URL")
    main_queue_url = os.environ.get("MAIN_QUEUE_URL")
    max_messages = int(event.get("maxMessages", os.environ.get("MAX_MESSAGES", "10")))

    if not dlq_url or not main_queue_url:
        error_msg = "Missing required environment variables: DLQ_URL and MAIN_QUEUE_URL"
        logger.error(error_msg)
        return {"statusCode": 500, "body": json.dumps({"error": error_msg})}

    logger.info(
        f"Starting DLQ redrive: dlq={dlq_url}, target={main_queue_url}, max_messages={max_messages}"
    )

    redriven_count = 0
    failed_count = 0
    errors = []

    # Get SQS client
    sqs = get_sqs_client()

    try:
        # Get approximate number of messages in DLQ
        dlq_attrs = sqs.get_queue_attributes(
            QueueUrl=dlq_url, AttributeNames=["ApproximateNumberOfMessages"]
        )
        approx_messages = int(
            dlq_attrs.get("Attributes", {}).get("ApproximateNumberOfMessages", "0")
        )
        logger.info(f"Approximate messages in DLQ: {approx_messages}")

        if approx_messages == 0:
            logger.info("No messages in DLQ to redrive")
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "No messages in DLQ",
                        "redrivenCount": 0,
                        "failedCount": 0,
                    }
                ),
            }

        # Process messages in batches
        while redriven_count < max_messages:
            # Receive messages from DLQ
            receive_count = min(
                10, max_messages - redriven_count
            )  # SQS max batch is 10
            response = sqs.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=receive_count,
                WaitTimeSeconds=1,  # Short poll
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])
            if not messages:
                logger.info("No more messages available in DLQ")
                break

            logger.info(f"Received {len(messages)} messages from DLQ")

            # Send messages to main queue and delete from DLQ
            for message in messages:
                # Check if we've reached the max_messages limit
                if redriven_count >= max_messages:
                    break

                try:
                    # Send to main queue
                    send_params = {
                        "QueueUrl": main_queue_url,
                        "MessageBody": message["Body"],
                    }

                    # Preserve message attributes if present
                    if "MessageAttributes" in message:
                        send_params["MessageAttributes"] = message["MessageAttributes"]

                    sqs.send_message(**send_params)

                    # Delete from DLQ only after successful send
                    sqs.delete_message(
                        QueueUrl=dlq_url, ReceiptHandle=message["ReceiptHandle"]
                    )

                    redriven_count += 1
                    logger.info(
                        f"Redriven message {message['MessageId']} ({redriven_count}/{max_messages})"
                    )

                except Exception as e:
                    failed_count += 1
                    error_msg = f"Failed to redrive message {message.get('MessageId', 'unknown')}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)

    except Exception as e:
        error_msg = f"Error during DLQ redrive: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "error": error_msg,
                    "redrivenCount": redriven_count,
                    "failedCount": failed_count,
                }
            ),
        }

    result = {
        "message": f"DLQ redrive completed",
        "redrivenCount": redriven_count,
        "failedCount": failed_count,
    }

    if errors:
        result["errors"] = errors[:10]  # Limit error list to avoid response size issues

    logger.info(f"DLQ redrive completed: {json.dumps(result)}")

    return {"statusCode": 200, "body": json.dumps(result)}
