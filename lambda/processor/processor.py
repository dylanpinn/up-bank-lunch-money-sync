import json
import logging
import os
from datetime import datetime

import boto3
import requests

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_manager = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

# API endpoints
UP_API_BASE = "https://api.up.com.au/api/v1"
LUNCHMONEY_API_BASE = "https://dev.lunchmoney.app/v1"


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
    Process transaction webhooks from SQS and sync to Lunch Money
    """
    for record in event["Records"]:
        try:
            # Decode and parse the webhook message
            webhook_data = json.loads(record["body"])

            # Extract event type from the correct location
            event_type = (
                webhook_data.get("data", {}).get("attributes", {}).get("eventType", "")
            )
            logger.info(f"Processing webhook type: {event_type}")

            # Process transaction events only
            if event_type in ("TRANSACTION_CREATED", "TRANSACTION_UPDATED"):
                process_transaction_event(webhook_data)
            elif event_type == "PING":
                logger.info("Received ping from Up Bank")
            else:
                logger.info(f"Ignoring webhook type: {event_type}")

        except Exception as e:
            logger.error(f"Error processing record: {str(e)}")
            # Re-raise to let SQS handle retry
            raise


def process_transaction_event(webhook_data):
    """
    Process a transaction webhook event and sync to Lunch Money
    """
    # Get secret ARNs from environment variables
    up_api_key_arn = os.environ["UP_API_KEY_ARN"]
    lunchmoney_api_key_arn = os.environ["LUNCHMONEY_API_KEY_ARN"]

    # Retrieve the actual secrets from Secrets Manager
    up_api_key = get_secret(up_api_key_arn)
    lunchmoney_api_key = get_secret(lunchmoney_api_key_arn)

    # Extract transaction ID from webhook data
    transaction_id = (
        webhook_data.get("data", {})
        .get("relationships", {})
        .get("transaction", {})
        .get("data", {})
        .get("id")
    )

    if not transaction_id:
        logger.error("No transaction ID found in webhook")
        return

    # Fetch full transaction details from Up API
    transaction = fetch_up_transaction(up_api_key, transaction_id)

    if not transaction:
        logger.error(f"Failed to fetch transaction {transaction_id}")
        return

    # Convert to Lunch Money format and check for round-up
    transactions_to_sync = convert_to_lunchmoney_format(transaction)

    # Send transaction(s) to Lunch Money
    # If round-up exists, this will be a list of 2 transactions
    if isinstance(transactions_to_sync, list):
        for txn in transactions_to_sync:
            sync_to_lunchmoney(lunchmoney_api_key, txn)
    else:
        sync_to_lunchmoney(lunchmoney_api_key, transactions_to_sync)


def get_account_mapping(up_account_id):
    """
    Lookup Lunch Money asset ID from DynamoDB using Up account ID
    """
    try:
        table_name = os.environ.get("ACCOUNT_MAPPING_TABLE")
        if not table_name:
            logger.warning("ACCOUNT_MAPPING_TABLE environment variable not set")
            return None

        table = dynamodb.Table(table_name)
        response = table.get_item(Key={"up_account_id": up_account_id})
        item = response.get("Item")

        if item:
            lunchmoney_id = item.get("lunchmoney_id")
            logger.info(
                f"Found account mapping: Up {up_account_id} -> Lunch Money {lunchmoney_id}"
            )
            return lunchmoney_id
        else:
            logger.warning(f"No account mapping found for Up account {up_account_id}")
            return None

    except Exception as e:
        logger.error(f"Error looking up account mapping: {str(e)}")
        return None


def get_category_mapping(up_category_id):
    """
    Lookup Lunch Money category ID from DynamoDB using Up category ID
    """
    try:
        table_name = os.environ.get("CATEGORY_MAPPING_TABLE")
        if not table_name:
            logger.warning("CATEGORY_MAPPING_TABLE environment variable not set")
            return None

        table = dynamodb.Table(table_name)
        response = table.get_item(Key={"up_category_id": up_category_id})
        item = response.get("Item")

        if item:
            lunchmoney_id = item.get("lunchmoney_id")
            logger.info(
                f"Found category mapping: Up {up_category_id} -> Lunch Money {lunchmoney_id}"
            )
            return lunchmoney_id
        else:
            logger.warning(
                f"No category mapping found for Up category {up_category_id}"
            )
            return None

    except Exception as e:
        logger.error(f"Error looking up category mapping: {str(e)}")
        return None


def fetch_up_transaction(api_key, transaction_id):
    """
    Fetch full transaction details from Up API
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            f"{UP_API_BASE}/transactions/{transaction_id}", headers=headers
        )

        if response.status_code == 200:
            return response.json().get("data")
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
    logger.debug(f"Up Transaction to Format: {up_transaction}")
    attributes = up_transaction.get("attributes", {})
    relationships = up_transaction.get("relationships", {})

    # Extract amount data (Up Bank stores amount as an object with value and currencyCode)
    amount = attributes.get("amount", {})
    amount_value = amount.get("value", "0") if isinstance(amount, dict) else amount
    currency = amount.get("currencyCode", "AUD") if isinstance(amount, dict) else "AUD"
    currency = currency.lower()  # Lunch Money expects lowercase currency codes

    # Convert to float and handle Up's format (negative for expenses)
    try:
        amount_float = float(amount_value)
    except (ValueError, TypeError):
        amount_float = 0.0

    # Map transaction type
    payee = attributes.get("description", "Unknown")

    # Handle Up Bank's message field
    message = attributes.get("message", "")
    notes = f"{message}" if message else ""

    # Extract transaction date
    transaction_date = (
        attributes.get("settledAt")
        or attributes.get("createdAt")
        or datetime.now().isoformat()
    )
    # Convert ISO datetime to YYYY-MM-DD format for Lunch Money
    if transaction_date and "T" in transaction_date:
        transaction_date = transaction_date.split("T")[0]

    lunchmoney_transaction = {
        "payee": payee,
        "amount": str(amount_float),  # Preserve sign: positive for income, negative for expenses
        "notes": notes,
        "date": transaction_date,
        "external_id": up_transaction.get(
            "id"
        ),  # Use Up's transaction ID for deduplication
        "currency": currency,
        # "status": "cleared" if attributes.get("status") == "SETTLED" else "uncleared",
        "status": "uncleared",
    }

    # Look up and add account mapping if available
    account_data = relationships.get("account", {}).get("data", {})
    if account_data:
        up_account_id = account_data.get("id")
        if up_account_id:
            lunchmoney_asset_id = get_account_mapping(up_account_id)
            if lunchmoney_asset_id:
                lunchmoney_transaction["asset_id"] = int(lunchmoney_asset_id)
            else:
                logger.warning(
                    f"No Lunch Money asset mapping found for Up account {up_account_id}"
                )

    # Look up and add category mapping if available
    category_data = relationships.get("category", {}).get("data", {})
    if category_data:
        up_category_id = category_data.get("id")
        if up_category_id:
            lunchmoney_category_id = get_category_mapping(up_category_id)
            if lunchmoney_category_id:
                lunchmoney_transaction["category_id"] = int(lunchmoney_category_id)
            else:
                logger.warning(
                    f"No Lunch Money category mapping found for Up category {up_category_id}"
                )

    # Check for round-up and create separate transaction if present
    roundup_data = attributes.get("roundUp")
    if roundup_data and roundup_data.get("amount"):
        logger.info(f"Transaction {up_transaction.get('id')} has round-up")
        
        roundup_amount_obj = roundup_data.get("amount", {})
        roundup_value = roundup_amount_obj.get("value", "0") if isinstance(roundup_amount_obj, dict) else roundup_amount_obj
        
        try:
            roundup_float = float(roundup_value)
        except (ValueError, TypeError):
            roundup_float = 0.0
        
        # Only create round-up transaction if amount is non-zero
        if roundup_float != 0.0:
            roundup_transaction = {
                "payee": "Round Up",
                "amount": str(roundup_float),
                "notes": f"Round up for: {payee}",
                "date": transaction_date,
                "external_id": f"{up_transaction.get('id')}-roundup",
                "currency": currency,
                "status": "uncleared",
            }
            
            # Use same account mapping for round-up
            if "asset_id" in lunchmoney_transaction:
                roundup_transaction["asset_id"] = lunchmoney_transaction["asset_id"]
            
            # Return both transactions as a list
            return [lunchmoney_transaction, roundup_transaction]

    return lunchmoney_transaction


def sync_to_lunchmoney(api_key, transaction):
    """
    Send transaction to Lunch Money API
    """
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "transactions": [transaction],
            "debit_as_negative": True,
            "apply_rules": True,
            "check_for_recurring": True,
        }

        logger.debug(f"Transaction to Sync: {transaction}")
        response = requests.post(
            f"{LUNCHMONEY_API_BASE}/transactions",
            headers=headers,
            json=payload,
            timeout=30,
        )

        logger.debug(f"Lunch Money Response (raw): {json.dumps(response.json())}")
        if response.status_code == 200:
            logger.info(
                f"Successfully synced transaction {transaction['external_id']} to Lunch Money"
            )
        else:
            logger.error(
                f"Lunch Money API error: {response.status_code} - {response.text}"
            )
            raise Exception(
                f"Failed to sync to Lunch Money: {response.status_code} - {response.text}"
            )

    except Exception as e:
        logger.error(f"Error syncing to Lunch Money: {str(e)}")
        raise
