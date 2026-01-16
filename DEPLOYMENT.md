# GitHub Actions Continuous Deployment Setup

This guide explains how to set up automatic deployment to AWS when code is pushed to the `main` branch.

## Overview

The CD pipeline automatically deploys changes to your AWS account when:
- Code is pushed to the `main` branch
- Tests pass successfully
- Build completes successfully

## Prerequisites

Before setting up CD, you need:
1. An AWS account with the necessary secrets already created in AWS Secrets Manager
2. GitHub repository with admin access
3. AWS IAM role configured for GitHub OIDC authentication

## Setup Steps

### 1. Deploy Bootstrap Stack (CDK - Recommended)

The **easiest and recommended** method is to use the provided CDK bootstrap stack, which creates everything for you.

#### Deploy the Bootstrap Stack

```bash
# Ensure you're authenticated with AWS
aws sts get-caller-identity

# Deploy the bootstrap stack
cdk deploy --app "python3 bootstrap_app.py"

# The output will show:
# BootstrapStack.GitHubActionsRoleArn = arn:aws:iam::123456789012:role/GitHubActionsDeployRole
# BootstrapStack.GitHubOIDCProviderArn = arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
# BootstrapStack.TrustPolicy = repo:dylanpinn/up-bank-lunch-money-sync:ref:refs/heads/main OR repo:dylanpinn/up-bank-lunch-money-sync:environment:production
```

**That's it!** The bootstrap stack creates:
- ✅ GitHub OIDC identity provider
- ✅ IAM role with proper trust policy
- ✅ All required AWS managed policies attached
- ✅ CloudFormation outputs with values for GitHub secrets

Save the `GitHubActionsRoleArn` output - you'll need it for GitHub secrets.

#### Customize (Optional)

To customize the GitHub repository, branch, or GitHub Environment name:

```bash
GITHUB_ORG=your-org GITHUB_REPO=your-repo GITHUB_BRANCH=main GITHUB_ENVIRONMENT=production \
  cdk deploy --app "python3 bootstrap_app.py"
```

### 1. Alternative: Manual Setup via AWS Console

If you prefer manual setup or cannot use CDK for the bootstrap:

<details>
<summary>Click to expand manual setup instructions</summary>

#### a. Create OIDC Identity Provider in AWS

1. Go to AWS Console → IAM → Identity providers
2. Click "Add provider"
3. Select "OpenID Connect"
4. Provider URL: `https://token.actions.githubusercontent.com`
5. Audience: `sts.amazonaws.com`
6. Click "Add provider"

#### b. Create IAM Role

1. Go to IAM → Roles → Create role
2. Select "Web identity"
3. Choose the OIDC provider you just created
4. Audience: `sts.amazonaws.com`
5. GitHub organization: `dylanpinn`
6. GitHub repository: `up-bank-lunch-money-sync`
7. GitHub branch: `main`
8. Click "Next"

#### c. Attach Policies

Attach the following AWS managed policies:
- `AWSCloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AWSLambda_FullAccess`
- `CloudWatchLogsFullAccess`
- `AmazonAPIGatewayAdministrator`
- `AmazonSQSFullAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonSNSFullAccess`
- `SecretsManagerReadWrite`
- `AmazonEventBridgeFullAccess`

#### d. Configure Trust Relationship

Edit the trust relationship to restrict to your repository:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": [
            "repo:dylanpinn/up-bank-lunch-money-sync:ref:refs/heads/main",
            "repo:dylanpinn/up-bank-lunch-money-sync:environment:production"
          ]
        }
      }
    }
  ]
}
```

#### e. Note the Role ARN

Save the role ARN, you'll need it for GitHub secrets:
```
arn:aws:iam::YOUR_ACCOUNT_ID:role/GitHubActionsDeployRole
```

</details>

### 2. Configure GitHub Secrets and Variables

The deploy job runs in the `production` GitHub Environment. Configure the following:

#### Environment Variable (in production environment)

1. Go to GitHub repository → Settings → Environments → production
2. Add environment variable:

| Variable Name | Description | Example Value |
|---------------|-------------|---------------|
| `AWS_REGION` | AWS region for deployment | `ap-southeast-2` |

#### Environment Secrets (in production environment)

1. Go to GitHub repository → Settings → Environments → production
2. Click "Add secret" for each:

| Secret Name | Description | Example Value |
|-------------|-------------|---------------|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC | `arn:aws:iam::123456789012:role/GitHubActionsDeployRole` |
| `WEBHOOK_SECRET_ARN` | ARN of webhook secret in Secrets Manager | `arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:up-bank-webhook-secret-XXXXXX` |
| `UP_API_KEY_ARN` | ARN of Up Bank API key in Secrets Manager | `arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:up-bank-api-key-XXXXXX` |
| `LUNCHMONEY_API_KEY_ARN` | ARN of Lunch Money API key in Secrets Manager | `arn:aws:secretsmanager:ap-southeast-2:123456789012:secret:lunchmoney-api-key-XXXXXX` |
| `NOTIFICATION_EMAIL` | (Optional) Email for CloudWatch alerts | `your-email@example.com` |

### 3. Get Secret ARNs from AWS

If you already created the secrets but don't have the ARNs:

```bash
# Get webhook secret ARN
aws secretsmanager describe-secret \
  --secret-id up-bank-webhook-secret \
  --query 'ARN' \
  --output text \
  --region ap-southeast-2

# Get Up Bank API key ARN
aws secretsmanager describe-secret \
  --secret-id up-bank-api-key \
  --query 'ARN' \
  --output text \
  --region ap-southeast-2

# Get Lunch Money API key ARN
aws secretsmanager describe-secret \
  --secret-id lunchmoney-api-key \
  --query 'ARN' \
  --output text \
  --region ap-southeast-2
```

### 4. Test the Deployment

1. Push a change to the `main` branch
2. Go to GitHub → Actions tab
3. Watch the "CI/CD Pipeline" workflow run
4. Verify deployment succeeds

Or trigger manually:
1. Go to GitHub → Actions → CI/CD Pipeline
2. Click "Run workflow"
3. Select branch: `main`
4. Click "Run workflow"

## Workflow Details

### Workflow File

Location: `.github/workflows/ci-cd.yml`

### Triggers

- **Automatic**: Push to `main` branch
- **Manual**: Via GitHub Actions UI

### Steps

1. ✅ Checkout code
2. ✅ Set up Python 3.14
3. ✅ Install Python dependencies
4. ✅ Install Node.js 24
5. ✅ Install AWS CDK
6. ✅ Configure AWS credentials (OIDC)
7. ✅ Run CDK diff (preview changes)
8. ✅ Deploy to AWS (if diff shows changes)

### Environment Variables

The workflow passes these environment variables to CDK:
- `WEBHOOK_SECRET_ARN`
- `UP_API_KEY_ARN`
- `LUNCHMONEY_API_KEY_ARN`
- `NOTIFICATION_EMAIL` (optional)

## Security Best Practices

### ✅ What We Do

- Use OIDC instead of long-lived AWS access keys
- Restrict IAM role to specific repository and branch
- Store sensitive ARNs as GitHub secrets
- Reference existing secrets in AWS Secrets Manager
- Use principle of least privilege for IAM permissions

### ❌ What We Don't Do

- Store actual API keys in GitHub (only ARNs)
- Use AWS access keys in GitHub secrets
- Deploy from feature branches
- Auto-approve CDK deployments without review

## Troubleshooting

### Deployment Fails: "Unable to assume role"

**Problem**: GitHub Actions can't authenticate with AWS

**Solutions**:
1. Verify OIDC provider is set up correctly in AWS IAM
2. Check role ARN in GitHub secrets matches IAM role
3. Verify trust relationship includes your repository
4. Ensure repository name and branch are correct

### Deployment Fails: "Secret not found"

**Problem**: CDK can't find secrets in AWS Secrets Manager

**Solutions**:
1. Verify secrets exist in AWS Secrets Manager
2. Check ARNs in GitHub secrets are correct (copy-paste full ARN)
3. Ensure IAM role has `secretsmanager:GetSecretValue` permission
4. Verify region matches where secrets are stored

### Deployment Fails: "No changes detected"

**Problem**: CDK doesn't see any changes to deploy

**Solutions**:
1. This is normal if no infrastructure changes were made
2. Check `cdk diff` output to see what changed
3. Code-only changes still trigger deployment but may not update infrastructure

### CDK Synth Fails

**Problem**: CloudFormation template generation fails

**Solutions**:
1. Run `cdk synth` locally to debug
2. Check Python syntax in CDK stack
3. Verify all dependencies are installed
4. Review CDK construct compatibility

## Monitoring Deployments

### GitHub Actions UI

1. Go to repository → Actions tab
2. Click on "CI/CD Pipeline" workflow
3. View deployment logs in real-time
4. Check for errors or warnings

### AWS CloudFormation

1. Go to AWS Console → CloudFormation
2. Find stack: `UpBankLunchMoneySyncStack`
3. View events and resources
4. Check for stack update failures

### AWS CloudWatch

After deployment, monitor Lambda functions:

```bash
# Webhook function logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-WebhookLambda --follow

# Processor function logs
aws logs tail /aws/lambda/UpBankLunchMoneySyncStack-ProcessorLambda --follow
```

## Rollback

If a deployment causes issues:

### Option 1: Revert and Redeploy

```bash
git revert HEAD
git push origin main
# Wait for automatic redeployment
```

### Option 2: Manual Rollback

```bash
# Locally, with previous code
cdk deploy

# Or rollback in CloudFormation console
# AWS Console → CloudFormation → Stack → Actions → Rollback
```

## Cost Considerations

GitHub Actions usage:
- Free for public repositories
- 2,000 minutes/month for private repositories (free tier)
- Each deployment takes ~3-5 minutes

AWS costs remain the same (~$2-5/month as documented in README).

## Managing the Bootstrap Stack

The bootstrap stack is separate from your application and only needs to be deployed once.

### View Bootstrap Stack

```bash
# View the stack
aws cloudformation describe-stacks --stack-name UpBankLunchMoneySyncBootstrap

# Get the role ARN output
aws cloudformation describe-stacks \
  --stack-name UpBankLunchMoneySyncBootstrap \
  --query 'Stacks[0].Outputs[?OutputKey==`GitHubActionsRoleArn`].OutputValue' \
  --output text
```

### Update Bootstrap Stack

If you need to change the GitHub repository, branch, or policies:

```bash
# Update with new configuration
GITHUB_ORG=your-org GITHUB_REPO=your-repo \
  cdk deploy --app "python3 bootstrap_app.py"
```

### Delete Bootstrap Stack

**Warning:** This will remove the OIDC provider and IAM role, breaking your CD pipeline.

```bash
cdk destroy --app "python3 bootstrap_app.py"
```

### Bootstrap Stack Components

The bootstrap stack creates and manages:

| Resource | Description | Managed by |
|----------|-------------|------------|
| OIDC Provider | GitHub Actions authentication | CloudFormation |
| IAM Role | Permissions for deployment | CloudFormation |
| Trust Policy | Restricts to specific repo/branch | CloudFormation |
| AWS Policies | 11 managed policies attached | CloudFormation |

All infrastructure is versioned in `up_bank_lunch_money_sync/bootstrap_stack.py`.

## Alternative: Using AWS Access Keys (Not Recommended)

If you cannot set up OIDC, you can use AWS access keys:

1. Create IAM user with programmatic access
2. Attach the same policies as above
3. Add these GitHub secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
4. Update `.github/workflows/ci-cd.yml`:

```yaml
- name: Configure AWS credentials
  uses: aws-actions/configure-aws-credentials@v4
  with:
    aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
    aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    aws-region: ${{ vars.AWS_REGION }}
```

**Note**: This is less secure and not recommended for production use.

## Next Steps

After setting up CD:

1. ✅ Test the deployment with a small change
2. ✅ Set up branch protection rules to require passing tests before merge
3. ✅ Configure CloudWatch alarms for Lambda failures
4. ✅ Document any custom deployment procedures
5. ✅ Set up staging environment (optional)

## Questions?

- Review [AWS CDK documentation](https://docs.aws.amazon.com/cdk/)
- Check [GitHub Actions documentation](https://docs.github.com/en/actions)
- See [AWS OIDC guide](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
