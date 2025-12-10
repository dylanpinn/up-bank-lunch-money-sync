# AGENTS.md

## Build/Lint/Test Commands

```bash
# Bootstrap GitHub Actions deployment (one-time setup)
cdk deploy --app "python3 bootstrap_app.py"

# Synthesize CloudFormation template
cdk synth

# Deploy to AWS manually (requires env vars: WEBHOOK_SECRET_ARN, UP_API_KEY_ARN, LUNCHMONEY_API_KEY_ARN)
cdk deploy

# Deploy with notification email
NOTIFICATION_EMAIL=your@email.com cdk deploy

# Destroy bootstrap stack
cdk destroy --app "python3 bootstrap_app.py"

# Run all tests
pytest tests/

# Run single test
pytest tests/unit/test_processor.py::TestProcessor::test_convert_to_lunchmoney_format_basic

# Run with coverage
pytest --cov=lambda --cov=up_bank_lunch_money_sync --cov-report=html tests/
```

## Continuous Deployment

The project uses GitHub Actions for automatic deployment to AWS:

- **Workflow**: `.github/workflows/deploy.yml`
- **Trigger**: Push to `main` branch or manual dispatch
- **Setup Guide**: See `DEPLOYMENT.md` for complete instructions

### Quick Deployment Check

```bash
# View recent deployments
gh run list --workflow=deploy.yml

# Watch current deployment
gh run watch

# View deployment logs
gh run view --log
```

## Code Style Guidelines

- **Python 3.14** with type hints where beneficial
- **Imports**: Standard library → third-party → local, alphabetized within groups
- **Logging**: Use `logging.getLogger()` with `INFO` level, structured messages
- **Error Handling**: Try/except blocks with logging, return meaningful error responses
- **AWS Clients**: Initialize at module level, use boto3 resource for DynamoDB
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Constants**: UPPER_SNAKE_CASE, defined at module level (API endpoints, timeouts)
- **Functions**: Docstrings for public functions, keep Lambda handlers focused
- **Timeouts**: 30-second HTTP timeouts for all external API calls