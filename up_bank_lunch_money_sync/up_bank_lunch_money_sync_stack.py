import os

from aws_cdk import Duration, RemovalPolicy, SecretValue, Stack
from aws_cdk import (
    aws_apigateway as apigw,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_lambda as _lambda,
)
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import (
    aws_sqs as sqs,
)
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct


class UpBankLunchMoneySyncStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Read secrets from environment variables
        webhook_secret_value = os.environ.get("UP_WEBHOOK_SECRET")
        up_api_key_value = os.environ.get("UP_API_KEY")
        lunchmoney_api_key_value = os.environ.get("LUNCHMONEY_API_KEY")

        # Validate environment variables
        if not all([webhook_secret_value, up_api_key_value, lunchmoney_api_key_value]):
            raise ValueError("Missing required environment variables for secrets")

        # Type narrowing: After validation, these are guaranteed to be strings
        assert webhook_secret_value is not None
        assert up_api_key_value is not None
        assert lunchmoney_api_key_value is not None

        # # Create DynamoDB table for account mapping
        account_mapping_table = dynamodb.TableV2(
            self,
            "AccountMappingTable",
            partition_key=dynamodb.Attribute(
                name="up_account_id", type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(
                max_read_request_units=5, max_write_request_units=5
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Create DynamoDB table for category mapping
        category_mapping_table = dynamodb.TableV2(
            self,
            "CategoryMappingTable",
            partition_key=dynamodb.Attribute(
                name="up_category_id", type=dynamodb.AttributeType.STRING
            ),
            billing=dynamodb.Billing.on_demand(
                max_read_request_units=5, max_write_request_units=5
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Create SQS queue for transaction processing
        queue = sqs.Queue(
            self,
            "UpWebhookQueue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
        )

        # Create secrets with values from environment
        webhook_secret = secretsmanager.Secret(
            self,
            "WebhookSecret",
            secret_name="up-bank-webhook-secret",
            secret_string_value=SecretValue.unsafe_plain_text(webhook_secret_value),
        )

        up_api_key_secret = secretsmanager.Secret(
            self,
            "UpApiKey",
            secret_name="up-bank-api-key",
            secret_string_value=SecretValue.unsafe_plain_text(up_api_key_value),
        )

        lunchmoney_api_key_secret = secretsmanager.Secret(
            self,
            "LunchmoneyApiKey",
            secret_name="lunchmoney-api-key",
            secret_string_value=SecretValue.unsafe_plain_text(lunchmoney_api_key_value),
        )

        # Webhook Lambda function
        webhook_lambda = PythonFunction(
            self,
            "WebhookFunction",
            entry="lambda/webhook",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_14,
            index="webhook.py",
            # code=_lambda.Code.from_asset("lambda/webhook"),
            environment={
                "SQS_QUEUE_URL": queue.queue_url,
                "WEBHOOK_SECRET_ARN": webhook_secret.secret_arn,
            },
            timeout=Duration.seconds(30),
        )

        # Processing Lambda function
        processor_lambda = PythonFunction(
            self,
            "ProcessorFunction",
            entry="lambda/processor",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_14,
            index="processor.py",
            environment={
                "UP_API_KEY_ARN": up_api_key_secret.secret_arn,
                "LUNCHMONEY_API_KEY_ARN": lunchmoney_api_key_secret.secret_arn,
                "ACCOUNT_MAPPING_TABLE": account_mapping_table.table_name,
                "CATEGORY_MAPPING_TABLE": category_mapping_table.table_name,
            },
            timeout=Duration.minutes(5),
        )

        # Account Sync Lambda function
        account_sync_lambda = PythonFunction(
            self,
            "AccountSyncFunction",
            runtime=_lambda.Runtime.PYTHON_3_14,
            entry="lambda/account_sync",
            handler="handler",
            index="account_sync.py",
            environment={
                "UP_API_KEY_ARN": up_api_key_secret.secret_arn,
                "LUNCHMONEY_API_KEY_ARN": lunchmoney_api_key_secret.secret_arn,
                "ACCOUNT_MAPPING_TABLE": account_mapping_table.table_name,
            },
            timeout=Duration.minutes(5),
        )

        # Category Sync Lambda function
        category_sync_lambda = PythonFunction(
            self,
            "CategorySyncFunction",
            runtime=_lambda.Runtime.PYTHON_3_14,
            entry="lambda/category_sync",
            handler="handler",
            index="category_sync.py",
            environment={
                "UP_API_KEY_ARN": up_api_key_secret.secret_arn,
                "LUNCHMONEY_API_KEY_ARN": lunchmoney_api_key_secret.secret_arn,
                "CATEGORY_MAPPING_TABLE": category_mapping_table.table_name,
            },
            timeout=Duration.minutes(5),
        )

        # Grant Lambda permissions to read secrets
        webhook_secret.grant_read(webhook_lambda)
        up_api_key_secret.grant_read(processor_lambda)
        lunchmoney_api_key_secret.grant_read(processor_lambda)
        up_api_key_secret.grant_read(account_sync_lambda)
        lunchmoney_api_key_secret.grant_read(account_sync_lambda)
        up_api_key_secret.grant_read(category_sync_lambda)
        lunchmoney_api_key_secret.grant_read(category_sync_lambda)

        # Grant DynamoDB permissions to account sync Lambda
        account_mapping_table.grant_read_write_data(account_sync_lambda)

        # Grant DynamoDB permissions to category sync Lambda
        category_mapping_table.grant_read_write_data(category_sync_lambda)

        # Grant DynamoDB read permissions to processor Lambda
        account_mapping_table.grant_read_data(processor_lambda)
        category_mapping_table.grant_read_data(processor_lambda)

        # Grant SQS permissions
        queue.grant_send_messages(webhook_lambda)
        queue.grant_consume_messages(processor_lambda)

        # Create API Gateway endpoint
        api = apigw.RestApi(
            self,
            "UpWebhookApi",
            rest_api_name="Up Webhook Service",
            description="This service processes Up Bank webhooks.",
        )

        # Add webhook endpoint
        webhook_integration = apigw.LambdaIntegration(webhook_lambda)
        api.root.add_resource("webhooks").add_resource("up").add_method(
            "POST", webhook_integration
        )

        # Set up SQS trigger for processor
        sqs_event_source = SqsEventSource(queue, batch_size=10)
        processor_lambda.add_event_source(sqs_event_source)

        # Create EventBridge rule to run account sync daily at 2 AM UTC
        account_sync_rule = events.Rule(
            self,
            "AccountSyncDailyRule",
            schedule=events.Schedule.cron(minute="0", hour="2"),
            description="Trigger account sync Lambda daily at 2 AM UTC",
        )
        account_sync_rule.add_target(targets.LambdaFunction(account_sync_lambda))

        # Create EventBridge rule to run category sync daily at 3 AM UTC
        category_sync_rule = events.Rule(
            self,
            "CategorySyncDailyRule",
            schedule=events.Schedule.cron(minute="0", hour="3"),
            description="Trigger category sync Lambda daily at 3 AM UTC",
        )
        category_sync_rule.add_target(targets.LambdaFunction(category_sync_lambda))
