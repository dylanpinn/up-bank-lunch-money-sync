from aws_cdk import (
	Stack, Duration, aws_lambda as _lambda,
    aws_sqs as sqs, aws_apigateway as apigw,
    aws_iam as iam
)
from constructs import Construct
from aws_cdk.aws_lambda_event_sources import SqsEventSource

class UpBankLunchMoneySyncStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SQS queue for transaction processing
        queue = sqs.Queue(
            self, "UpWebhookQueue",
            visibility_timeout=Duration.seconds(300),
            retention_period=Duration.days(14)
        )

        # Webhook Lambda function
        webhook_lambda = _lambda.Function(
            self, "WebhookFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="webhook.handler",
            code=_lambda.Code.from_asset("lambda/webhook"),
            environment={
                "SQS_QUEUE_URL": queue.queue_url,
                "WEBHOOK_SECRET": "your-webhook-secret"
            },
            timeout=Duration.seconds(30)
        )

        # Processing Lambda function
        processor_lambda = _lambda.Function(
            self, "ProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_9,
            handler="processor.handler",
            code=_lambda.Code.from_asset("lambda/processor"),
            environment={
                "LUNCHMONEY_API_KEY": "your-lunchmoney-api-key",
                "UP_API_KEY": "your-up-api-key"
            },
            timeout=Duration.minutes(5)
        )

        # Grant SQS permissions
        queue.grant_send_messages(webhook_lambda)
        queue.grant_consume_messages(processor_lambda)

        # Create API Gateway endpoint
        api = apigw.RestApi(
            self, "UpWebhookApi",
            rest_api_name="Up Webhook Service",
            description="This service processes Up Bank webhooks."
        )

        # Add webhook endpoint
        webhook_integration = apigw.LambdaIntegration(webhook_lambda)
        api.root.add_resource("webhooks").add_resource("up").add_method(
            "POST", webhook_integration
        )

        # Set up SQS trigger for processor
        sqs_event_source = SqsEventSource(queue, batch_size=10)
        processor_lambda.add_event_source(sqs_event_source)
