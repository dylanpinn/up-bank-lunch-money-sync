import json
import os
import requests
import logging
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# API endpoints
UP_API_BASE = "https://api.up.com.au/api/v1"
LUNCHMONEY_API_BASE = "https://dev.lunchmoney.app/api/v1"

def handler(event, context):
    """
    Process transaction webhooks from SQS and sync to Lunch Money
    """
    for record in event['Records']:
        try:
            # Decode and parse the webhook message
            webhook_data = json.loads(record['body'])

            logger.info(f"Processing webhook type: {webhook_data.get('type')}")

            # Process transaction events only
            if webhook_data.get('type') == 'transaction.created' or webhook_data.get('type') == 'transaction.updated':
                process_transaction_event(webhook_data)

            # Handle other event types as needed
            elif webhook_data.get('type') == 'ping':
                logger.info("Received ping from Up Bank")

            else:
                logger.info(f"Ignoring webhook type: {webhook_data.get('type')}")

        except Exception as e:
            logger.error(f"Error processing record: {str(e)}")
            # Re-raise to let SQS handle retry
            raise

def process_transaction_event(webhook_data):
    """
    Process a transaction webhook event and sync to Lunch Money
    """
    # Get environment variables
    up_api_key = os.environ['UP_API_KEY']
    lunchmoney_api_key = os.environ['LUNCHMONEY_API_KEY']

    # Extract transaction data
    transaction_data = webhook_data.get('data', {}).get('relationships', {}).get('transaction', {}).get('data', {})
    transaction_id = transaction_data.get('id')

    if not transaction_id:
        logger.error("No transaction ID found in webhook")
        return

    # Fetch full transaction details from Up API
    transaction = fetch_up_transaction(up_api_key, transaction_id)

    if not transaction:
        logger.error(f"Failed to fetch transaction {transaction_id}")
        return

    # Convert to Lunch Money format
    lunchmoney_transaction = convert_to_lunchmoney_format(transaction)

    # Send to Lunch Money
    sync_to_lunchmoney(lunchmoney_api_key, lunchmoney_transaction)

def fetch_up_transaction(api_key, transaction_id):
    """
    Fetch full transaction details from Up API
    """
    try:
        headers = {'Authorization': f'Bearer {api_key}'}
        response = requests.get(
            f"{UP_API_BASE}/transactions/{transaction_id}",
            headers=headers
        )

        if response.status_code == 200:
            return response.json().get('data')
        else:
            logger.error(f"Up API error: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error fetching from Up API: {str(e)}")
        return None

def convert_to_lunchmoney_format(up_transaction):
    """
    Convert Up transaction format to Lunch Money format
    """
    attributes = up_transaction.get('attributes', {})

    # Convert amount (Up Bank uses cents, Lunch Money uses dollars)
    amount = attributes.get('amount', {})  # Up amount is in cents/base units
    amount_value = amount.get('value', '0') if isinstance(amount, dict) else amount

    # Convert to float and handle Up's format (negative for expenses)
    try:
        amount_float = float(amount_value) / 100  # Convert from cents
    except (ValueError, TypeError):
        amount_float = 0.0

    # Map transaction type
    payee = attributes.get('description', 'Unknown')

    # Handle Up Bank's message field
    message = attributes.get('message', '')
    notes = f"{message}" if message else ""

    lunchmoney_transaction = {
        'payee': payee,
        'amount': str(abs(amount_float)),  # Lunch Money expects positive amounts
        'type': 'expense' if amount_float < 0 else 'income',
        'notes': notes,
        'date': attributes.get('settledAt', attributes.get('createdAt', datetime.now().isoformat())),
        'external_id': up_transaction.get('id'),  # Use Up's transaction ID for deduplication
        'currency': attributes.get('value', {}).get('currency', 'AUD') if isinstance(attributes.get('value'), dict) else 'AUD',
        'status': 'cleared' if attributes.get('status') == 'SETTLED' else 'pending'
    }

    return lunchmoney_transaction

def sync_to_lunchmoney(api_key, transaction):
    """
    Send transaction to Lunch Money API
    """
    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        payload = {
            'transactions': [transaction]
        }

        response = requests.post(
            f"{LUNCHMONEY_API_BASE}/transactions",
            headers=headers,
            json=payload
        )

        if response.status_code == 200:
            logger.info(f"Successfully synced transaction {transaction['external_id']} to Lunch Money")
        else:
            logger.error(f"Lunch Money API error: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error syncing to Lunch Money: {str(e)}")
        raise
