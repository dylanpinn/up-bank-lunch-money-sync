# Dead Letter Queue (DLQ) Redrive

This document explains the DLQ redrive functionality for failed transaction processing in the Up Bank to Lunch Money sync service.

## Overview

When the transaction processor Lambda fails to process a message after multiple attempts (5 retries by default), the message is automatically moved to a Dead Letter Queue (DLQ). The DLQ redrive functionality allows you to reprocess these failed messages after resolving the underlying issues.

## Architecture

```
┌─────────────┐    Failed after     ┌─────────────┐
│   Main      │    5 attempts       │    Dead     │
│   Queue     ├────────────────────>│   Letter    │
│             │                     │   Queue     │
└─────────────┘                     └──────┬──────┘
      ^                                    │
      │                                    │
      │    ┌───────────────────┐          │
      └────┤  DLQ Redrive      │<─────────┘
           │  Lambda           │
           └───────────────────┘
```

## How It Works

1. **Automatic Failure Detection**: When a transaction fails to process 5 times, it's moved to the DLQ
2. **CloudWatch Alarm**: An alarm triggers when messages appear in the DLQ (if notifications are enabled)
3. **Manual/Scheduled Redrive**: You can manually invoke the redrive Lambda or enable automatic scheduled redrives
4. **Reprocessing**: Messages are moved from DLQ back to the main queue for another processing attempt

## Manual Invocation

### Using AWS CLI

After deployment, get the Lambda function name from the stack outputs:

```bash
# Get the Lambda function name
aws cloudformation describe-stacks \
  --stack-name UpBankLunchMoneySyncStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DlqRedriveLambdaName`].OutputValue' \
  --output text
```

Invoke the redrive Lambda:

```bash
# Redrive with default settings (max 10 messages)
aws lambda invoke \
  --function-name <LAMBDA_FUNCTION_NAME> \
  --payload '{}' \
  response.json

# Redrive with custom max messages
aws lambda invoke \
  --function-name <LAMBDA_FUNCTION_NAME> \
  --payload '{"maxMessages": 50}' \
  response.json

# View the response
cat response.json
```

### Using AWS Console

1. Navigate to **AWS Lambda** in the AWS Console
2. Find the function named `UpBankLunchMoneySyncStack-DlqRedriveFunction...`
3. Click **Test** tab
4. Create a new test event:
   - Event name: `RedriveTest`
   - Event JSON:
     ```json
     {
       "maxMessages": 10
     }
     ```
5. Click **Test** to invoke

### Response Format

The Lambda returns a JSON response:

```json
{
  "statusCode": 200,
  "body": {
    "message": "DLQ redrive completed",
    "redrivenCount": 5,
    "failedCount": 0,
    "errors": []
  }
}
```

## Scheduled Automatic Redrive

To enable automatic redrive on a schedule (e.g., every 6 hours), uncomment the EventBridge rule in the CDK stack:

```python
# In up_bank_lunch_money_sync_stack.py (around line 291)

# Optional: Create EventBridge rule for scheduled automatic redrive
# Uncomment the following to enable automatic redrive every 6 hours
dlq_redrive_rule = events.Rule(
    self,
    "DlqRedriveScheduleRule",
    schedule=events.Schedule.cron(minute="0", hour="*/6"),
    description="Trigger DLQ redrive every 6 hours",
)
dlq_redrive_rule.add_target(targets.LambdaFunction(dlq_redrive_lambda))
```

Then redeploy:

```bash
cdk deploy
```

You can adjust the schedule using cron expressions:
- Every 6 hours: `hour="*/6"`
- Every 12 hours: `hour="*/12"`
- Daily at 4 AM UTC: `minute="0", hour="4"`
- Twice daily (6 AM and 6 PM UTC): `minute="0", hour="6,18"`

## Monitoring

### Check DLQ Message Count

```bash
# Get DLQ name
DLQ_NAME=$(aws cloudformation describe-stacks \
  --stack-name UpBankLunchMoneySyncStack \
  --query 'Stacks[0].Outputs[?OutputKey==`DlqName`].OutputValue' \
  --output text)

# Get DLQ URL
DLQ_URL=$(aws sqs get-queue-url --queue-name $DLQ_NAME --query 'QueueUrl' --output text)

# Check message count
aws sqs get-queue-attributes \
  --queue-url $DLQ_URL \
  --attribute-names ApproximateNumberOfMessages \
  --query 'Attributes.ApproximateNumberOfMessages' \
  --output text
```

### CloudWatch Logs

View redrive Lambda logs:

```bash
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-DlqRedriveFunction --follow
```

### CloudWatch Alarms

If you've configured email notifications (via `NOTIFICATION_EMAIL` environment variable), you'll receive alerts when:
- Messages appear in the DLQ
- The redrive Lambda encounters errors
- The redrive Lambda exceeds duration thresholds

## Configuration

### Environment Variables

The redrive Lambda uses these environment variables (set automatically by CDK):

- `DLQ_URL`: URL of the Dead Letter Queue
- `MAIN_QUEUE_URL`: URL of the main processing queue
- `MAX_MESSAGES`: Default maximum messages to redrive per invocation (default: 10)

### Adjusting Default Max Messages

Modify the CDK stack:

```python
# In up_bank_lunch_money_sync_stack.py
environment={
    "DLQ_URL": dlq.queue_url,
    "MAIN_QUEUE_URL": queue.queue_url,
    "MAX_MESSAGES": "50",  # Change from 10 to 50
},
```

## Common Scenarios

### Scenario 1: API Outage

**Problem**: Lunch Money API was down, causing 100 transactions to fail

**Solution**:
1. Wait for Lunch Money API to recover
2. Invoke redrive Lambda multiple times or increase `maxMessages`:
   ```bash
   aws lambda invoke \
     --function-name <LAMBDA_NAME> \
     --payload '{"maxMessages": 100}' \
     response.json
   ```

### Scenario 2: Missing Category Mapping

**Problem**: Transactions failed because category mapping doesn't exist

**Solution**:
1. Run category sync Lambda to update mappings:
   ```bash
   aws lambda invoke \
     --function-name <CATEGORY_SYNC_LAMBDA_NAME> \
     --payload '{}' \
     response.json
   ```
2. After sync completes, redrive failed transactions:
   ```bash
   aws lambda invoke \
     --function-name <DLQ_REDRIVE_LAMBDA_NAME> \
     --payload '{}' \
     response.json
   ```

### Scenario 3: Bad Data in DLQ

**Problem**: Some messages in DLQ are malformed and will never succeed

**Solution**:
1. Manually inspect DLQ messages in AWS Console
2. Delete bad messages:
   ```bash
   # Receive message
   aws sqs receive-message --queue-url $DLQ_URL
   
   # Delete specific message
   aws sqs delete-message \
     --queue-url $DLQ_URL \
     --receipt-handle <RECEIPT_HANDLE>
   ```
3. Redrive remaining valid messages

## Best Practices

1. **Investigate Before Redrive**: Always check CloudWatch Logs to understand why messages failed before redriving
2. **Fix Root Cause**: Resolve the underlying issue (API outage, missing mappings, etc.) before redriving
3. **Start Small**: Test with a small `maxMessages` value first to verify the fix works
4. **Monitor Reprocessing**: Watch CloudWatch Logs during redrive to ensure messages process successfully
5. **Avoid Infinite Loops**: Ensure the issue is resolved or messages will end up back in the DLQ
6. **DLQ Retention**: Messages are retained in the DLQ for 14 days, then automatically deleted

## Troubleshooting

### Redrive Lambda Times Out

**Symptom**: Lambda times out before processing all messages

**Solution**: 
- Reduce `maxMessages` per invocation
- Invoke multiple times
- Consider increasing Lambda timeout (currently 5 minutes)

### Messages Return to DLQ

**Symptom**: Redriven messages fail again and return to DLQ

**Solution**:
- The underlying issue is not resolved
- Check processor Lambda logs for error details
- Verify API keys are valid
- Verify category/account mappings exist

### Permission Errors

**Symptom**: Lambda cannot read from DLQ or write to main queue

**Solution**:
- Verify IAM permissions in CDK stack
- Redeploy stack: `cdk deploy`

## Limitations

- Maximum 10 messages per receive operation (SQS limit)
- DLQ retention period: 14 days
- Lambda timeout: 5 minutes
- After 5 failed attempts in main queue, messages move to DLQ

## Related Documentation

- [AWS SQS Dead Letter Queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [AWS Lambda Error Handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html)
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment guide
- [README.md](../README.md) - Project overview