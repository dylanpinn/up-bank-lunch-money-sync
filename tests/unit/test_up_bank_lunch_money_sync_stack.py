import aws_cdk as core
import aws_cdk.assertions as assertions

from up_bank_lunch_money_sync.up_bank_lunch_money_sync_stack import UpBankLunchMoneySyncStack

# example tests. To run these tests, uncomment this file along with the example
# resource in up_bank_lunch_money_sync/up_bank_lunch_money_sync_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = UpBankLunchMoneySyncStack(app, "up-bank-lunch-money-sync")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
