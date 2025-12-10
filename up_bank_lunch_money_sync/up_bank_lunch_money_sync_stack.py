import os

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import (
    aws_apigateway as apigw,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_cloudwatch_actions as actions,
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
    aws_sns as sns,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct


class UpBankLunchMoneySyncStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Read optional notification email from environment variable
        notification_email_value = os.environ.get("NOTIFICATION_EMAIL")

        # Create SNS topic for notifications (only if email is provided)
        notification_topic = None
        if notification_email_value:
            notification_topic = sns.Topic(
                self,
                "LambdaFailureNotificationTopic",
                display_name="Lambda Failure Notifications",
                topic_name="lambda-failure-notifications",
            )

            # Subscribe email to SNS topic
            sns.Subscription(
                self,
                "EmailSubscription",
                endpoint=notification_email_value,
                protocol=sns.SubscriptionProtocol.EMAIL,
                topic=notification_topic,
            )

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

        # Create DLQ for failed transaction processing
        dlq = sqs.Queue(
            self,
            "UpWebhookDLQ",
            retention_period=Duration.days(14),
        )

        # Create SQS queue for transaction processing with DLQ
        queue = sqs.Queue(
            self,
            "UpWebhookQueue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=5,
                queue=dlq,
            ),
        )

        # Reference existing secrets from AWS Secrets Manager
        # These secrets must be pre-created before deployment
        # ARNs are read from environment variables
        webhook_secret_arn = os.environ.get(
            "WEBHOOK_SECRET_ARN",
            "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:up-bank-webhook-secret-XXXXXX",
        )
        up_api_key_arn = os.environ.get(
            "UP_API_KEY_ARN",
            "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:up-bank-api-key-XXXXXX",
        )
        lunchmoney_api_key_arn = os.environ.get(
            "LUNCHMONEY_API_KEY_ARN",
            "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:lunchmoney-api-key-XXXXXX",
        )

        webhook_secret = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "WebhookSecret",
            secret_complete_arn=webhook_secret_arn,
        )

        up_api_key_secret = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "UpApiKey",
            secret_complete_arn=up_api_key_arn,
        )

        lunchmoney_api_key_secret = secretsmanager.Secret.from_secret_complete_arn(
            self,
            "LunchmoneyApiKey",
            secret_complete_arn=lunchmoney_api_key_arn,
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
        sqs_event_source = SqsEventSource(
            queue, batch_size=10, max_batching_window=Duration.seconds(30)
        )
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

        # Create CloudWatch Alarms for Lambda monitoring (only if notification topic exists)
        if notification_topic:
            self._create_lambda_alarms(
                webhook_lambda, "Webhook", notification_topic, Duration.seconds(24)
            )
            self._create_lambda_alarms(
                processor_lambda, "Processor", notification_topic, Duration.minutes(4)
            )
            self._create_lambda_alarms(
                account_sync_lambda,
                "AccountSync",
                notification_topic,
                Duration.minutes(4),
            )
            self._create_lambda_alarms(
                category_sync_lambda,
                "CategorySync",
                notification_topic,
                Duration.minutes(4),
            )

            # DLQ alarm for failed messages
            dlq_alarm = cloudwatch.Alarm(
                self,
                "DLQAlarm",
                alarm_name="Processor DLQ Messages",
                alarm_description="Alarm when DLQ has messages indicating failed processing",
                metric=cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessagesVisible",
                    dimensions_map={"QueueName": dlq.queue_name},
                    statistic="Maximum",
                ),
                threshold=1,
                evaluation_periods=1,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )
            dlq_alarm.add_alarm_action(actions.SnsAction(notification_topic))
            dlq_alarm.add_ok_action(actions.SnsAction(notification_topic))

    def _create_lambda_alarms(
        self,
        lambda_function: _lambda.Function,
        function_name: str,
        notification_topic: sns.Topic,
        duration_threshold: Duration,
    ) -> None:
        """Create CloudWatch alarms for a Lambda function."""

        # Error rate alarm
        error_alarm = cloudwatch.Alarm(
            self,
            f"{function_name}ErrorAlarm",
            alarm_name=f"{function_name} Lambda Errors",
            alarm_description=f"Alarm when {function_name} Lambda has errors",
            metric=lambda_function.metric_errors(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        error_alarm.add_alarm_action(actions.SnsAction(notification_topic))
        error_alarm.add_ok_action(actions.SnsAction(notification_topic))

        # Duration alarm (80% of timeout)
        duration_alarm = cloudwatch.Alarm(
            self,
            f"{function_name}DurationAlarm",
            alarm_name=f"{function_name} Lambda Duration",
            alarm_description=f"Alarm when {function_name} Lambda duration exceeds threshold",
            metric=lambda_function.metric_duration(),
            threshold=duration_threshold.to_milliseconds(),
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        duration_alarm.add_alarm_action(actions.SnsAction(notification_topic))
        duration_alarm.add_ok_action(actions.SnsAction(notification_topic))

        # Throttle alarm
        throttle_alarm = cloudwatch.Alarm(
            self,
            f"{function_name}ThrottleAlarm",
            alarm_name=f"{function_name} Lambda Throttles",
            alarm_description=f"Alarm when {function_name} Lambda is throttled",
            metric=lambda_function.metric_throttles(),
            threshold=1,
            evaluation_periods=1,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        throttle_alarm.add_alarm_action(actions.SnsAction(notification_topic))
        throttle_alarm.add_ok_action(actions.SnsAction(notification_topic))
