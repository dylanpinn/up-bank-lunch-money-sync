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
    Sync categories from Up Bank to Lunch Money and store mapping in DynamoDB
    """
    try:
        # Get configuration from environment variables
        up_api_key_arn = os.environ["UP_API_KEY_ARN"]
        lunchmoney_api_key_arn = os.environ["LUNCHMONEY_API_KEY_ARN"]
        table_name = os.environ["CATEGORY_MAPPING_TABLE"]

        # Retrieve API keys from Secrets Manager
        up_api_key = get_secret(up_api_key_arn)
        lunchmoney_api_key = get_secret(lunchmoney_api_key_arn)

        # Get DynamoDB table
        table = dynamodb.Table(table_name)

        # Fetch all categories from Up Bank
        logger.info("Fetching categories from Up Bank")
        up_categories = fetch_up_categories(up_api_key)
        logger.info(f"Found {len(up_categories)} categories from Up Bank")

        # Fetch existing categories from Lunch Money
        logger.info("Fetching existing categories from Lunch Money")
        lunchmoney_categories = fetch_lunchmoney_categories(lunchmoney_api_key)
        logger.info(f"Found {len(lunchmoney_categories)} categories in Lunch Money")

        # Process each Up category
        synced_count = 0
        for up_category in up_categories:
            try:
                category_id = up_category.get("id")
                attributes = up_category.get("attributes", {})
                category_name = attributes.get("name")
                parent_id = None

                # Check if category has a parent (subcategory)
                parent_relationship = up_category.get("relationships", {}).get(
                    "parent", {}
                )
                if parent_relationship.get("data"):
                    parent_id = parent_relationship["data"].get("id")

                logger.info(
                    f"Processing category: {category_name} (ID: {category_id}, Parent: {parent_id})"
                )

                # Check if category already exists in DynamoDB
                existing_mapping = get_existing_mapping(table, category_id)

                if existing_mapping:
                    logger.info(
                        f"Category {category_id} already mapped to Lunch Money ID {existing_mapping['lunchmoney_id']}"
                    )
                    synced_count += 1
                    continue

                # Create or find category in Lunch Money
                lunchmoney_id = create_or_find_lunchmoney_category(
                    lunchmoney_api_key,
                    lunchmoney_categories,
                    category_name,
                    parent_id,
                )

                if lunchmoney_id:
                    # Save mapping to DynamoDB
                    save_category_mapping(
                        table,
                        category_id,
                        lunchmoney_id,
                        category_name,
                        parent_id,
                    )
                    logger.info(
                        f"Successfully synced {category_name}: Up ID {category_id} -> Lunch Money ID {lunchmoney_id}"
                    )
                    synced_count += 1
                else:
                    logger.error(f"Failed to sync category {category_name}")

            except Exception as e:
                logger.error(
                    f"Error processing category {up_category.get('id')}: {str(e)}"
                )
                continue

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Successfully synced {synced_count} of {len(up_categories)} categories",
                    "synced_count": synced_count,
                    "total_categories": len(up_categories),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error in category sync handler: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def fetch_up_categories(api_key):
    """
    Fetch all categories from Up Bank API
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        categories = []
        url = f"{UP_API_BASE}/categories"

        # Paginate through all categories
        while url:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                data = response.json()
                categories.extend(data.get("data", []))

                # Check for next page
                next_link = data.get("links", {}).get("next")
                url = next_link
            else:
                logger.error(f"Up API error: {response.status_code} - {response.text}")
                raise Exception(
                    f"Failed to fetch Up categories: {response.status_code} - {response.text}"
                )

        return categories

    except Exception as e:
        logger.error(f"Error fetching from Up API: {str(e)}")
        raise


def fetch_lunchmoney_categories(api_key):
    """
    Fetch all categories from Lunch Money API
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        response = requests.get(
            f"{LUNCHMONEY_API_BASE}/categories", headers=headers, timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("categories", [])
        else:
            logger.error(
                f"Lunch Money API error: {response.status_code} - {response.text}"
            )
            # Return empty list if endpoint doesn't exist or fails
            return []

    except Exception as e:
        logger.error(f"Error fetching from Lunch Money API: {str(e)}")
        return []


def create_or_find_lunchmoney_category(
    api_key, existing_categories, category_name, parent_id
):
    """
    Create a new category in Lunch Money or find existing one by name
    """
    try:
        # Check if category already exists by name
        for category in existing_categories:
            if category.get("name") == category_name:
                logger.info(
                    f"Found existing Lunch Money category: {category_name} (ID: {category.get('id')})"
                )
                return category.get("id")

        # Create new category
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "name": category_name,
            "description": f"Synced from Up Bank",
        }

        logger.info(f"Creating new Lunch Money category: {payload}")
        response = requests.post(
            f"{LUNCHMONEY_API_BASE}/categories",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            category_id = data.get("category_id")
            logger.info(f"Created Lunch Money category with ID: {category_id}")
            return category_id
        else:
            logger.error(
                f"Lunch Money API error: {response.status_code} - {response.text}"
            )
            raise Exception(
                f"Failed to create Lunch Money category: {response.status_code} - {response.text}"
            )

    except Exception as e:
        logger.error(f"Error creating Lunch Money category: {str(e)}")
        raise


def get_existing_mapping(table, up_category_id):
    """
    Check if category mapping already exists in DynamoDB
    """
    try:
        response = table.get_item(Key={"up_category_id": up_category_id})
        return response.get("Item")
    except Exception as e:
        logger.error(f"Error checking existing mapping: {str(e)}")
        return None


def save_category_mapping(
    table, up_category_id, lunchmoney_id, category_name, parent_id
):
    """
    Save category mapping to DynamoDB
    """
    try:
        item = {
            "up_category_id": up_category_id,
            "lunchmoney_id": str(lunchmoney_id),
            "category_name": category_name,
        }

        if parent_id:
            item["up_parent_id"] = parent_id

        table.put_item(Item=item)
        logger.info(f"Saved mapping to DynamoDB: {up_category_id} -> {lunchmoney_id}")
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {str(e)}")
        raise
