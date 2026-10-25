# AGENTS.md

Project instructions for coding agents working in this repository.

## Project Overview

AWS serverless microservice that syncs Up Bank transaction webhooks to Lunch
Money, plus scheduled account and category syncs. Built with AWS CDK (Python
3.14): API Gateway, Lambda, SQS, DynamoDB, EventBridge, Secrets Manager.

See `README.md` for setup and `DEPLOYMENT.md` for deployment details.

## Commands

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt -r tests/requirements.txt
pytest tests/

cdk synth
cdk diff
cdk deploy
```

All tests are unit tests with AWS and HTTP mocked; never make real AWS or
external API calls from tests.

## Non-obvious Constraints

- **Secrets:** the stack references pre-existing Secrets Manager secrets and
  needs `WEBHOOK_SECRET_ARN`, `UP_API_KEY_ARN`, and `LUNCHMONEY_API_KEY_ARN` set
  to their ARNs before `cdk synth`/`cdk deploy`. Never embed credentials in
  templates, environment variables, or CDK state.
- **Lunch Money endpoint:** every Lambda currently points at the development
  endpoint `https://dev.lunchmoney.app/v1`; change `LUNCHMONEY_API_BASE` in each
  Lambda for production.
- **Webhook security:** HMAC-SHA256 verification of
  `X-Up-Authenticity-Signature` is enabled; missing or invalid signatures return
  `403`.
- **Retries:** processor failures are retried by SQS up to 5 times, then land in
  the DLQ, which is redriven every 6 hours. Re-raise errors that SQS should
  retry.
- **Data safety:** DynamoDB mapping tables use `RemovalPolicy.RETAIN` and
  mappings survive stack deletion.
- **HTTP:** all external API calls use a 30-second timeout.

## Project Conventions

- Initialize AWS clients at module level; use the boto3 resource API for
  DynamoDB.
- Use `logging.getLogger()` with structured `INFO` messages.
- Mappings are Up Bank ID -> Lunch Money ID; category mappings include the
  parent category ID. Preserve pagination and parent/child handling in category
  sync.

## Architecture

```
Up Bank -> API Gateway -> webhook Lambda -> SQS -> processor Lambda -> Lunch Money
                                              |
                                          DynamoDB mappings
```

Other Lambdas: `account_sync` (daily 2 AM UTC), `category_sync` (daily 3 AM
UTC), `dlq_redrive` (every 6 hours). See `docs/DLQ_REDRIVE.md`.
