import os

import aws_cdk as core
import aws_cdk.assertions as assertions

from up_bank_lunch_money_sync.up_bank_lunch_money_sync_stack import UpBankLunchMoneySyncStack

# example tests. To run these tests, uncomment this file along with the example
# resource in up_bank_lunch_money_sync/up_bank_lunch_money_sync_stack.py
def test_sqs_queue_created():
    # Set valid ARNs for testing
    os.environ["WEBHOOK_SECRET_ARN"] = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-webhook-abcdef"
    os.environ["UP_API_KEY_ARN"] = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-up-api-abcdef"
    os.environ["LUNCHMONEY_API_KEY_ARN"] = "arn:aws:secretsmanager:us-east-1:123456789012:secret:test-lunchmoney-abcdef"
    
    app = core.App()
    stack = UpBankLunchMoneySyncStack(app, "up-bank-lunch-money-sync")
    template = assertions.Template.from_stack(stack)

    # Test SQS queue has correct visibility timeout (12 minutes = 720 seconds)
    template.has_resource_properties("AWS::SQS::Queue", {
        "VisibilityTimeout": 720
    })
