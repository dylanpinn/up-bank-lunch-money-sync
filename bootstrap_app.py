#!/usr/bin/env python3
"""
Bootstrap app for deploying GitHub Actions OIDC infrastructure.
Deploy this once to set up the OIDC provider and IAM role.

Usage:
    cdk deploy --app "python3 bootstrap_app.py"
    
Or set environment variables:
    GITHUB_ORG=your-org GITHUB_REPO=your-repo cdk deploy --app "python3 bootstrap_app.py"
"""
import os

import aws_cdk as cdk

from up_bank_lunch_money_sync.bootstrap_stack import BootstrapStack

app = cdk.App()

# Get region from environment or use default
region = os.environ.get("AWS_REGION", os.environ.get("CDK_DEFAULT_REGION"))

BootstrapStack(
    app,
    "UpBankLunchMoneySyncBootstrap",
    description="Bootstrap stack for GitHub Actions OIDC and IAM role",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=region,
    ),
)

app.synth()
