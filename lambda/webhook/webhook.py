import json
import os
import hmac
import hashlib
import base64
import boto3
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize SQS client
sqs = boto3.client('sqs')

def handler(event, context):
    """
    Handle incoming Up Bank webhooks, verify signature, and queue for processing
    """
    try:
        # Get webhook configuration from environment variables
        webhook_secret = os.environ['WEBHOOK_SECRET']
        queue_url = os.environ['SQS_QUEUE_URL']

        # Extract webhook signature from headers
        signature = event['headers'].get('X-Up-Authenticity-Signature')
        if not signature:
            logger.error("Missing signature header")
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Missing signature'})
            }

        # Get the raw body for signature verification
        body = event['body'] if isinstance(event['body'], str) else json.dumps(event['body'])

        # Verify webhook signature using HMAC-SHA256
        expected_signature = base64.b64encode(
            hmac.new(
                webhook_secret.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')

        if not hmac.compare_digest(signature, expected_signature):
            logger.error("Invalid signature")
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Invalid signature'})
            }

        # Parse webhook payload
        webhook_data = json.loads(body)
        logger.info(f"Received webhook: {webhook_data.get('type', 'unknown')}")

        # Send the webhook data to SQS for processing
        sqs_response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(webhook_data),
            MessageAttributes={
                'webhook_type': {
                    'StringValue': webhook_data.get('type', 'unknown'),
                    'DataType': 'String'
                }
            }
        )

        logger.info(f"Message queued with ID: {sqs_response['MessageId']}")

        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Webhook queued successfully'})
        }

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }
