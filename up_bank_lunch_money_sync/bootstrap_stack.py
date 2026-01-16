import os

import aws_cdk as cdk
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class BootstrapStack(Stack):
    """
    Bootstrap stack that sets up GitHub Actions OIDC provider and IAM role.
    Deploy this stack once manually, then use the outputs in GitHub secrets.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get configuration from environment or use defaults
        github_org = os.environ.get("GITHUB_ORG", "dylanpinn")
        github_repo = os.environ.get("GITHUB_REPO", "up-bank-lunch-money-sync")
        github_branch = os.environ.get("GITHUB_BRANCH", "main")
        github_environment = os.environ.get("GITHUB_ENVIRONMENT", "production")

        # Create GitHub OIDC provider
        github_provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOIDCProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
        )

        # Create role for GitHub Actions with trust policy
        github_role = iam.Role(
            self,
            "GitHubActionsDeployRole",
            assumed_by=iam.OpenIdConnectPrincipal(
                github_provider,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": [
                            f"repo:{github_org}/{github_repo}:ref:refs/heads/{github_branch}",
                            f"repo:{github_org}/{github_repo}:environment:{github_environment}",
                        ]
                    },
                },
            ),
            role_name="GitHubActionsDeployRole",
            description="Role for GitHub Actions to deploy CDK stacks",
            max_session_duration=cdk.Duration.hours(1),
        )

        # Add inline policy with all required permissions
        # Using inline policy to avoid the 10 managed policies per role limit
        github_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudformation:*",
                    "iam:*",
                    "s3:*",
                    "lambda:*",
                    "logs:*",
                    "apigateway:*",
                    "sqs:*",
                    "dynamodb:*",
                    "sns:*",
                    "secretsmanager:*",
                    "events:*",
                    "ssm:GetParameter",
                    "sts:GetCallerIdentity",
                ],
                resources=["*"],
            )
        )

        # Output the role ARN and provider ARN for use in GitHub secrets
        CfnOutput(
            self,
            "GitHubActionsRoleArn",
            value=github_role.role_arn,
            description="ARN of the GitHub Actions IAM role - add this to GitHub secrets as AWS_ROLE_ARN",
            export_name="GitHubActionsRoleArn",
        )

        CfnOutput(
            self,
            "GitHubOIDCProviderArn",
            value=github_provider.open_id_connect_provider_arn,
            description="ARN of the GitHub OIDC provider",
            export_name="GitHubOIDCProviderArn",
        )

        CfnOutput(
            self,
            "TrustPolicy",
            value=(
                f"repo:{github_org}/{github_repo}:ref:refs/heads/{github_branch} OR "
                f"repo:{github_org}/{github_repo}:environment:{github_environment}"
            ),
            description="Trust policy condition(s) for the GitHub Actions role",
        )
