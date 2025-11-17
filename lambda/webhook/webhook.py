import base64
import hashlib
import hmac
import json
import logging
import os

import boto3

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sqs = boto3.client("sqs")
secrets_manager = boto3.client("secretsmanager")


def get_secret(secret_arn):
    """
    Retrieve a secret value from AWS Secrets Manager
    """
    try:
        response = secrets_manager.get_secret_value(SecretId=secret_arn)
        if "SecretString" in response:
            return response["SecretString"]
        else:
            return response["SecretBinary"]
    except Exception as e:
        logger.error(f"Error retrieving secret: {str(e)}")
        raise


def handler(event, context):
    """
    Handle incoming Up Bank webhooks, verify signature, and queue for processing
    """
    try:
        # Get webhook configuration from environment variables and Secrets Manager
        webhook_secret_arn = os.environ["WEBHOOK_SECRET_ARN"]
        queue_url = os.environ["SQS_QUEUE_URL"]

        # Retrieve the webhook secret from Secrets Manager
        webhook_secret = get_secret(webhook_secret_arn)

        # Extract webhook signature from headers
        signature = event["headers"].get("X-Up-Authenticity-Signature")
        if not signature:
            logger.error("Missing signature header")
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Missing signature"}),
            }

        # Get the raw body for signature verification
        if event.get("isBase64Encoded"):
            body_bytes = base64.b64decode(event["body"])
            body_str = "<base64 decoded>"
        else:
            body_str = (
                event["body"]
                if isinstance(event["body"], str)
                else json.dumps(event["body"])
            )
            body_bytes = body_str.encode("utf-8")

        # Verify webhook signature using HMAC-SHA256
        expected_signature = hmac.new(
            webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid signature")
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Invalid signature"}),
            }

        body = (
            event["body"]
            if isinstance(event["body"], str)
            else json.dumps(event["body"])
        )

        # Parse webhook payload
        webhook_data = json.loads(body)
        logger.debug(f"Received webhook (raw): {body}")

        # Extract event type from the correct location
        event_type = (
            webhook_data.get("data", {})
            .get("attributes", {})
            .get("eventType", "unknown")
        )
        logger.info(f"Received webhook: {event_type}")

        # Send the webhook data to SQS for processing
        sqs_response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(webhook_data),
            MessageAttributes={
                "webhook_type": {
                    "StringValue": event_type,
                    "DataType": "String",
                }
            },
        )

        logger.info(f"Message queued with ID: {sqs_response['MessageId']}")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Webhook queued successfully"}),
        }

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Internal server error"}),
        }
