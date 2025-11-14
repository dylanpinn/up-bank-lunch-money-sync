# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an AWS serverless microservice that synchronizes financial data between Up Bank (Australian neobank) and Lunch Money (personal finance app). The system receives real-time transaction webhooks from Up Bank and syncs them to Lunch Money, along with periodic account and category synchronization.

**Key Technologies:** AWS CDK, Python 3.14, Lambda, DynamoDB, SQS, EventBridge, Secrets Manager

## Common Development Commands

### Prerequisites
```bash
# Activate Python virtual environment
source .venv/bin/activate

# Set required environment variables for deployment
export UP_WEBHOOK_SECRET="your-webhook-secret"
export UP_API_KEY="your-up-bank-api-key"
export LUNCHMONEY_API_KEY="your-lunchmoney-api-key"
```

### Building & Deployment
```bash
# Synthesize CloudFormation template
cdk synth

# Deploy to AWS
cdk deploy

# Compare with deployed stack
cdk diff

# List all stacks
cdk ls
```

### Testing
```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Set test environment variables (for local testing)
export UP_WEBHOOK_SECRET="test-secret"
export UP_API_KEY="test-api-key"
export LUNCHMONEY_API_KEY="test-lunchmoney-key"

# Run all tests
pytest tests/

# Run with coverage report
pytest --cov=lambda --cov=up_bank_lunch_money_sync --cov-report=html tests/

# Run specific test file
pytest tests/unit/lambda/test_processor.py

# Run single test
pytest tests/unit/lambda/test_processor.py::TestProcessor::test_convert_to_lunchmoney_format_basic

# Run with verbose output
pytest -v tests/

# Run failed tests first
pytest --ff tests/
```

## Architecture & Structure

### High-Level Data Flow
```
Up Bank Webhook → API Gateway → Webhook Lambda → SQS Queue
                                                     ↓
                            Processor Lambda ← DynamoDB (Mappings)
                                ↓
                        Lunch Money API
```

### Three Key Workflows

1. **Real-time Transaction Processing**
   - Webhook Lambda (lambda/webhook/webhook.py) receives transactions from Up Bank
   - Verifies HMAC-SHA256 signatures
   - Queues events to SQS for asynchronous processing
   - Processor Lambda (lambda/processor/processor.py) picks up messages from SQS
   - Fetches full transaction details from Up Bank API
   - Converts format and looks up mappings in DynamoDB
   - Posts to Lunch Money API

2. **Daily Account Synchronization** (scheduled 2 AM UTC)
   - Account Sync Lambda (lambda/account_sync/account_sync.py)
   - Fetches all accounts from Up Bank
   - Creates or finds corresponding Lunch Money assets
   - Stores ID mappings in DynamoDB (account_mapping_table)

3. **Daily Category Synchronization** (scheduled 3 AM UTC)
   - Category Sync Lambda (lambda/category_sync/category_sync.py)
   - Fetches all categories from Up Bank (with pagination)
   - Handles parent-child category relationships
   - Creates or finds corresponding Lunch Money categories
   - Stores ID mappings in DynamoDB (category_mapping_table)

### Infrastructure Definition
**File:** `up_bank_lunch_money_sync/up_bank_lunch_money_sync_stack.py` (224 lines)

Defines all AWS resources:
- **SQS Queue:** Buffers transactions for processing (batch size: 10)
- **DynamoDB Tables:**
  - `account_mapping_table` - Maps Up Bank account IDs to Lunch Money asset IDs
  - `category_mapping_table` - Maps Up Bank category IDs to Lunch Money category IDs (includes parent-child relationships)
- **Lambda Functions:** webhook, processor, account_sync, category_sync (30s, 5min, 5min, 5min timeouts respectively)
- **API Gateway:** HTTP endpoint for Up Bank webhooks
- **EventBridge Rules:** Daily triggers at 2 AM and 3 AM UTC
- **Secrets Manager:** Stores webhook secret, Up Bank API key, Lunch Money API key

### Lambda Functions

| Function | File | Purpose |
|----------|------|---------|
| webhook | lambda/webhook/webhook.py (114 lines) | HTTP endpoint handler, signature verification, SQS queuing |
| processor | lambda/processor/processor.py (298 lines) | Transaction processing, data conversion, API calls |
| account_sync | lambda/account_sync/account_sync.py (269 lines) | Account synchronization and mapping storage |
| category_sync | lambda/category_sync/category_sync.py (284 lines) | Category synchronization with pagination and parent-child support |

### Shared Utilities
- **get_secret()** - Retrieves credentials from AWS Secrets Manager
- All Lambda functions use shared environment variable resolution

## Testing

### Test Coverage Overview
59+ unit tests across 6 test files:
- **test_helpers.py** - Secret retrieval tests
- **test_webhook.py** - Webhook handler tests (signature verification, SQS)
- **test_processor.py** - Transaction processing tests (15+ cases)
- **test_account_sync.py** - Account sync tests (10+ cases)
- **test_category_sync.py** - Category sync tests with pagination (11+ cases)
- **test_up_bank_lunch_money_sync_stack.py** - CDK infrastructure tests (12+ cases)

### Testing Strategy
- All tests are unit tests with mocked external dependencies (AWS services, HTTP APIs)
- No real AWS or API calls are made
- Tests follow Arrange-Act-Assert pattern
- Each test is isolated and independent
- See TESTING.md for detailed information

## Key Implementation Details

### Webhook Signature Verification
- Uses HMAC-SHA256 for verification
- Currently disabled in code (noted with comment)
- Implementation in `lambda/webhook/webhook.py`

### Data Mapping Strategy
- DynamoDB tables store bidirectional mappings
- Account mapping: simple lookup (up_id → lm_id)
- Category mapping: includes parent ID for hierarchy support
- Lookups critical for transaction routing

### API Timeouts
- All HTTP requests use 30-second timeout to prevent hanging
- Configured in each Lambda function

### Development vs Production
- Currently uses Lunch Money development endpoint: `dev.lunchmoney.app`
- DynamoDB tables set to RETAIN on deletion (data preservation)

## Configuration Files

- **cdk.json** - CDK configuration, feature flags, watch excludes
- **app.py** - CDK app entry point
- **requirements.txt** - Production dependencies (CDK, boto3, requests)
- **requirements-dev.txt** - Development dependencies
- **tests/requirements.txt** - Test dependencies (pytest, moto)
- **mise.toml** - Tool versions (Python 3.14, Node.js latest)

## Important Notes

1. **Environment Variables Required for Deployment**
   - UP_WEBHOOK_SECRET, UP_API_KEY, LUNCHMONEY_API_KEY must be set before `cdk deploy`

2. **Current Limitations**
   - Webhook signature verification is disabled
   - Uses Lunch Money development endpoint
   - Category sync has pagination (handle large category lists)

3. **Data Retention**
   - DynamoDB tables explicitly retained on stack deletion to prevent accidental data loss
   - Mappings persist across deployments

4. **SQS Processing**
   - Batch size of 10 for efficient processing
   - Lambda reserved concurrency can be increased for higher throughput

5. **Scheduled Syncs**
   - Account sync: 2 AM UTC daily
   - Category sync: 3 AM UTC daily
   - Times can be adjusted in `up_bank_lunch_money_sync_stack.py`
