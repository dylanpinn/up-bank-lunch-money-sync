# AGENTS.md

## Build/Lint/Test Commands

```bash
# Synthesize CloudFormation template
cdk synth

# Deploy to AWS (requires env vars: UP_WEBHOOK_SECRET, UP_API_KEY, LUNCHMONEY_API_KEY)
cdk deploy

# Run all tests
pytest tests/

# Run single test
pytest tests/unit/test_processor.py::TestProcessor::test_convert_to_lunchmoney_format_basic

# Run with coverage
pytest --cov=lambda --cov=up_bank_lunch_money_sync --cov-report=html tests/
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