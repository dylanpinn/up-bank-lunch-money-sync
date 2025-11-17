import json
import logging
import os

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
    Sync bank accounts from Up to Lunch Money and store mapping in DynamoDB
    """
    try:
        # Get configuration from environment variables
        up_api_key_arn = os.environ["UP_API_KEY_ARN"]
        lunchmoney_api_key_arn = os.environ["LUNCHMONEY_API_KEY_ARN"]
        table_name = os.environ["ACCOUNT_MAPPING_TABLE"]

        # Retrieve API keys from Secrets Manager
        up_api_key = get_secret(up_api_key_arn)
        lunchmoney_api_key = get_secret(lunchmoney_api_key_arn)

        # Get DynamoDB table
        table = dynamodb.Table(table_name)

        # Fetch all accounts from Up Bank
        logger.info("Fetching accounts from Up Bank")
        up_accounts = fetch_up_accounts(up_api_key)
        logger.info(f"Found {len(up_accounts)} accounts from Up Bank")

        # Fetch existing assets from Lunch Money
        logger.info("Fetching existing assets from Lunch Money")
        lunchmoney_assets = fetch_lunchmoney_assets(lunchmoney_api_key)
        logger.info(f"Found {len(lunchmoney_assets)} assets in Lunch Money")

        # Process each Up account
        synced_count = 0
        for up_account in up_accounts:
            try:
                account_id = up_account.get("id")
                attributes = up_account.get("attributes", {})
                account_name = attributes.get("displayName")
                account_type = attributes.get("accountType")
                balance_obj = attributes.get("balance", {})
                balance = float(balance_obj.get("value", 0)) if balance_obj else 0.0

                logger.info(f"Processing account: {account_name} (ID: {account_id})")

                # Check if account already exists in DynamoDB
                existing_mapping = get_existing_mapping(table, account_id)

                if existing_mapping:
                    logger.info(
                        f"Account {account_id} already mapped to Lunch Money ID {existing_mapping['lunchmoney_id']}"
                    )
                    synced_count += 1
                    continue

                # Create or find account in Lunch Money
                lunchmoney_id = create_or_find_lunchmoney_asset(
                    lunchmoney_api_key,
                    lunchmoney_assets,
                    account_name,
                    account_type,
                    balance,
                )

                if lunchmoney_id:
                    # Save mapping to DynamoDB
                    save_account_mapping(
                        table,
                        account_id,
                        lunchmoney_id,
                        account_name,
                        account_type,
                    )
                    logger.info(
                        f"Successfully synced {account_name}: Up ID {account_id} -> Lunch Money ID {lunchmoney_id}"
                    )
                    synced_count += 1
                else:
                    logger.error(f"Failed to sync account {account_name}")

            except Exception as e:
                logger.error(
                    f"Error processing account {up_account.get('id')}: {str(e)}"
                )
                continue

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Successfully synced {synced_count} of {len(up_accounts)} accounts",
                    "synced_count": synced_count,
                    "total_accounts": len(up_accounts),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error in account sync handler: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def fetch_up_accounts(api_key):
    """
    Fetch all accounts from Up Bank API
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        accounts = []
        url = f"{UP_API_BASE}/accounts"
        
        # Paginate through all accounts
        while url:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                accounts.extend(data.get("data", []))

                # Check for next page
                next_link = data.get("links", {}).get("next")
                url = next_link
            else:
                logger.error(f"Up API error: {response.status_code} - {response.text}")
                raise Exception(
                    f"Failed to fetch Up accounts: {response.status_code} - {response.text}"
                )

        return accounts
    except Exception as e:
        logger.error(f"Error fetching from Up API: {str(e)}")
        raise


def fetch_lunchmoney_assets(api_key):
    """
    Fetch all assets (accounts) from Lunch Money API
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            f"{LUNCHMONEY_API_BASE}/assets", headers=headers, timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("assets", [])
        else:
            logger.error(
                f"Lunch Money API error: {response.status_code} - {response.text}"
            )
            # Return empty list if endpoint doesn't exist or fails
            return []

    except Exception as e:
        logger.error(f"Error fetching from Lunch Money API: {str(e)}")
        return []


def create_or_find_lunchmoney_asset(
    api_key, existing_assets, account_name, account_type, balance
):
    """
    Create a new asset in Lunch Money or find existing one by name
    """
    try:
        # Check if asset already exists by name
        for asset in existing_assets:
            if asset.get("name") == account_name:
                logger.info(
                    f"Found existing Lunch Money asset: {account_name} (ID: {asset.get('id')})"
                )
                return asset.get("id")

        # Create new asset
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Map Up account types to Lunch Money types
        type_mapping = {
            "SAVER": "cash",
            "TRANSACTIONAL": "cash",
        }

        payload = {
            "type_name": type_mapping.get(account_type, "cash"),
            "name": account_name,
            "balance": balance,
            "currency": "aud",
        }

        logger.info(f"Creating new Lunch Money asset: {payload}")
        response = requests.post(
            f"{LUNCHMONEY_API_BASE}/assets", headers=headers, json=payload, timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            asset_id = data.get("asset_id")
            logger.info(f"Created Lunch Money asset with ID: {asset_id}")
            return asset_id
        else:
            logger.error(
                f"Lunch Money API error: {response.status_code} - {response.text}"
            )
            raise Exception(
                f"Failed to create Lunch Money asset: {response.status_code} - {response.text}"
            )

    except Exception as e:
        logger.error(f"Error creating Lunch Money asset: {str(e)}")
        raise


def get_existing_mapping(table, up_account_id):
    """
    Check if account mapping already exists in DynamoDB
    """
    try:
        response = table.get_item(Key={"up_account_id": up_account_id})
        return response.get("Item")
    except Exception as e:
        logger.error(f"Error checking existing mapping: {str(e)}")
        return None


def save_account_mapping(
    table, up_account_id, lunchmoney_id, account_name, account_type
):
    """
    Save account mapping to DynamoDB
    """
    try:
        table.put_item(
            Item={
                "up_account_id": up_account_id,
                "lunchmoney_id": str(lunchmoney_id),
                "account_name": account_name,
                "account_type": account_type,
            }
        )
        logger.info(f"Saved mapping to DynamoDB: {up_account_id} -> {lunchmoney_id}")
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {str(e)}")
        raise
