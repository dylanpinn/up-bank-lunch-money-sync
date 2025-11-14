# Up Bank → Lunch Money Sync

Automatically sync transactions from Up Bank (Australian neobank) to Lunch Money using serverless webhooks hosted on AWS.

This system receives real-time transaction events from Up Bank via webhooks and syncs them to Lunch Money, while also periodically synchronizing accounts and spending categories.

## Features

- 🔄 **Real-time Transaction Sync** - Transactions synced immediately via webhooks
- 📅 **Scheduled Syncs** - Accounts and categories synchronized daily
- 🔒 **Secure** - Credentials stored in AWS Secrets Manager, webhook signature verification
- ⚡ **Serverless** - Built on AWS Lambda, auto-scaling, pay-per-use
- 🧪 **Fully Tested** - 59+ unit tests with comprehensive coverage

## Prerequisites

### Required Tools
- **Python 3.14** (or use `mise` for automatic version management)
- **Node.js** (latest LTS)
- **AWS CLI** - [Install](https://aws.amazon.com/cli/)
- **AWS CDK** - `npm install -g aws-cdk`
- **AWS Account** - With credentials configured locally

### Required API Keys
- **Up Bank API Key** - From your [Up Bank Developer Settings](https://developer.up.com.au/)
- **Lunch Money API Key** - From your [Lunch Money Settings](https://my.lunchmoney.app/developers)
- **Up Bank Webhook Secret** - Generate a strong random string

## Quick Setup

### 1. Clone & Install Dependencies

```bash
git clone <repository-url>
cd up-bank-lunch-money-sync

# Activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Set Up AWS Credentials

Configure AWS CLI with your credentials:
```bash
aws configure
```

Verify your configuration:
```bash
aws sts get-caller-identity
```

### 3. Set Environment Variables

```bash
export UP_WEBHOOK_SECRET="your-generated-webhook-secret"
export UP_API_KEY="your-up-bank-api-key"
export LUNCHMONEY_API_KEY="your-lunch-money-api-key"
```

Save these in `.env` or your shell profile for convenience.

### 4. Deploy to AWS

```bash
# Verify the CloudFormation template
cdk synth

# Deploy to AWS (first time will create new resources)
cdk deploy

# The output will show your webhook URL, e.g.:
# UpBankLunchMoneySyncStack.WebhookURL = https://xxx.execute-api.us-east-1.amazonaws.com/prod/webhook
```

### 5. Configure Up Bank Webhooks

1. Go to your [Up Bank Developer Settings](https://developer.up.com.au/)
2. Create a new webhook:
   - **URL:** Use the webhook URL from the CDK deploy output
   - **Secret Token:** Use your `UP_WEBHOOK_SECRET` value
   - **Events:** Select `TRANSACTION_CREATED`

3. Test the webhook connection in Up Bank developer console

## How It Works

### Architecture Overview

```
┌─────────────┐
│  Up Bank    │
│  Webhook    │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐
│   API Gateway        │
│   /prod/webhook      │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Webhook Lambda       │
│ - Verify signature   │
│ - Queue to SQS       │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│    SQS Queue         │
│  (batch size: 10)    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ Processor Lambda     │
│ - Fetch details      │
│ - Look up mappings   │
│ - Convert format     │
│ - Post to Lunch $    │
└──────┬───────────────┘
       │
  ┌────┴─────┐
  ▼          ▼
 DynamoDB  Lunch Money
(Mappings)    API
```

### What Gets Synced

1. **Transactions** (Real-time)
   - Transaction amount, description, merchant
   - Account mapping (Up Bank → Lunch Money)
   - Category mapping (Up Bank → Lunch Money)

2. **Accounts** (Daily at 2 AM UTC)
   - Syncs all Up Bank accounts
   - Creates/updates Lunch Money assets
   - Stores account ID mappings

3. **Categories** (Daily at 3 AM UTC)
   - Syncs all Up Bank spending categories
   - Handles parent-child category relationships
   - Stores category ID mappings

## Development

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Set test environment variables
export UP_WEBHOOK_SECRET="test-secret"
export UP_API_KEY="test-api-key"
export LUNCHMONEY_API_KEY="test-lunchmoney-key"

# Run all tests
pytest tests/

# Run with coverage report
pytest --cov=lambda --cov=up_bank_lunch_money_sync --cov-report=html tests/

# Run specific test file
pytest tests/unit/lambda/test_processor.py -v

# Run single test
pytest tests/unit/lambda/test_processor.py::TestProcessor::test_convert_to_lunchmoney_format_basic -v
```

See [TESTING.md](TESTING.md) for detailed testing documentation.

### Project Structure

```
up-bank-lunch-money-sync/
├── app.py                              # CDK app entry point
├── requirements.txt                    # Production dependencies
├── requirements-dev.txt                # Development dependencies
│
├── up_bank_lunch_money_sync/           # CDK infrastructure
│   └── up_bank_lunch_money_sync_stack.py
│
├── lambda/                             # Lambda functions
│   ├── webhook/webhook.py              # Webhook handler
│   ├── processor/processor.py           # Transaction processor
│   ├── account_sync/account_sync.py     # Account sync
│   └── category_sync/category_sync.py   # Category sync
│
└── tests/                              # Test suite (59+ tests)
    └── unit/
        ├── lambda/                     # Lambda function tests
        └── test_up_bank_lunch_money_sync_stack.py
```

### Common Development Tasks

```bash
# View CDK stack diff
cdk diff

# Deploy updates to existing stack
cdk deploy

# List all resources
cdk ls

# View CloudFormation template
cdk synth

# Destroy stack (deletes AWS resources)
cdk destroy
```

### Making Changes

1. Edit lambda files in `lambda/*/` or CDK stack in `up_bank_lunch_money_sync/`
2. Run tests to verify changes: `pytest tests/`
3. Deploy changes: `cdk deploy`

## Troubleshooting

### Webhook Not Receiving Events
- Verify webhook URL is correct in Up Bank settings
- Check that webhook secret matches `UP_WEBHOOK_SECRET`
- Test webhook connection in Up Bank developer console
- Check CloudWatch logs for Lambda errors

### Transactions Not Syncing
- Verify API keys are correct in Secrets Manager
- Check that accounts/categories have been synced (see scheduled sync times)
- Review Processor Lambda logs in CloudWatch
- Ensure Lunch Money API endpoint is correct (currently: dev.lunchmoney.app)

### Deployment Fails
- Run `cdk synth` to check for template errors
- Verify AWS credentials: `aws sts get-caller-identity`
- Check IAM permissions in your AWS account
- Review CDK logs for detailed error messages

### Tests Failing
- Ensure all three environment variables are set (UP_WEBHOOK_SECRET, UP_API_KEY, LUNCHMONEY_API_KEY)
- Run `pip install -r tests/requirements.txt` to install test dependencies
- Check that Python 3.14+ is being used: `python3 --version`

## Monitoring & Logs

### View Logs in CloudWatch
```bash
# Webhook function logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-WebhookLambda --follow

# Processor function logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-ProcessorLambda --follow

# Account sync logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-AccountSyncLambda --follow

# Category sync logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-CategorySyncLambda --follow
```

### Check SQS Queue Depth
```bash
aws sqs get-queue-attributes \
  --queue-url <queue-url> \
  --attribute-names ApproximateNumberOfMessages
```

## Known Limitations

- Webhook signature verification is currently disabled
- Uses Lunch Money development endpoint (dev.lunchmoney.app)
- Category sync handles pagination but processes all categories daily

## Updating Scheduled Sync Times

Edit `up_bank_lunch_money_sync/up_bank_lunch_money_sync_stack.py`:
- Account sync: Change `schedule=events.Schedule.cron(hour="2")`
- Category sync: Change `schedule=events.Schedule.cron(hour="3")`

Then run `cdk deploy` to update.

## Cost Estimation

Typical monthly costs (varies by transaction volume):
- Lambda: ~$0.20 (up to 1M invocations)
- DynamoDB: ~$1 (on-demand pricing)
- SQS: <$0.01 (1M requests free tier)
- API Gateway: ~$0.35 (1M requests)
- Secrets Manager: $0.40

**Total: ~$2-5 per month** for typical household usage

## License

See LICENSE file for details.

## Support

For issues or questions:
1. Check TESTING.md for test-related questions
2. Review CLAUDE.md for architecture details
3. Check CloudWatch logs for runtime errors
4. Verify all API keys and configuration are correct
