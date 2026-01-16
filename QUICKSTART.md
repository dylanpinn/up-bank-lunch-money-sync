# Quick Start: Automated Deployment Setup

Get continuous deployment running in 5 minutes!

## Prerequisites

- ✅ AWS CLI configured (`aws sts get-caller-identity` works)
- ✅ AWS CDK installed (`npm install -g aws-cdk`)
- ✅ Python dependencies installed (`pip install -r requirements.txt`)
- ✅ AWS Secrets Manager secrets already created (see README.md)

## Step 1: Deploy Bootstrap Stack (2 minutes)

```bash
# Deploy the bootstrap infrastructure
cdk deploy --app "python3 bootstrap_app.py"
```

**Output example:**
```
UpBankLunchMoneySyncBootstrap.GitHubActionsRoleArn = arn:aws:iam::123456789012:role/GitHubActionsDeployRole
UpBankLunchMoneySyncBootstrap.GitHubOIDCProviderArn = arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com
UpBankLunchMoneySyncBootstrap.TrustPolicy = repo:dylanpinn/up-bank-lunch-money-sync:ref:refs/heads/main OR repo:dylanpinn/up-bank-lunch-money-sync:environment:production
```

✅ **What this creates:**
- GitHub OIDC identity provider
- IAM role for GitHub Actions
- All required AWS policies

## Step 2: Get Secret ARNs (1 minute)

```bash
# Get webhook secret ARN
aws secretsmanager describe-secret \
  --secret-id up-bank-webhook-secret \
  --query 'ARN' --output text

# Get Up Bank API key ARN
aws secretsmanager describe-secret \
  --secret-id up-bank-api-key \
  --query 'ARN' --output text

# Get Lunch Money API key ARN
aws secretsmanager describe-secret \
  --secret-id lunchmoney-api-key \
  --query 'ARN' --output text
```

## Step 3: Add GitHub Secrets and Variables (2 minutes)

### A. Add Environment Variable

Go to: **GitHub repository → Settings → Environments → production**

Add environment variable:

| Variable Name | Value Source |
|---------------|--------------|
| `AWS_REGION` | Your AWS region (e.g., `ap-southeast-2`) |

### B. Add Environment Secrets

In the same production environment, add these 5 secrets:

| Secret Name | Value Source |
|-------------|--------------|
| `AWS_ROLE_ARN` | From Step 1 output: `GitHubActionsRoleArn` |
| `WEBHOOK_SECRET_ARN` | From Step 2: webhook secret ARN |
| `UP_API_KEY_ARN` | From Step 2: Up Bank API key ARN |
| `LUNCHMONEY_API_KEY_ARN` | From Step 2: Lunch Money API key ARN |
| `NOTIFICATION_EMAIL` | Your email (optional) |

## Step 4: Test Deployment (30 seconds)

### Option A: Manual Test
1. Go to: **GitHub → Actions → Deploy to AWS**
2. Click **"Run workflow"**
3. Select branch: **main**
4. Click **"Run workflow"**
5. Watch it deploy! 🚀

### Option B: Automatic Test
```bash
# Make a small change
echo "# Test deployment" >> README.md

# Commit and push
git add README.md
git commit -m "Test: trigger CD pipeline"
git push origin main

# Watch in GitHub Actions
```

## ✅ Done!

Your deployment pipeline is now active and will automatically deploy on every push to `main`!

---

## What Just Happened?

### Bootstrap Stack (One-Time)
```
┌─────────────────────────────────┐
│  UpBankLunchMoneySyncBootstrap  │
│  (CloudFormation Stack)         │
├─────────────────────────────────┤
│  - GitHub OIDC Provider         │
│  - IAM Role: GitHubActions...   │
│  - Managed Policies (11)        │
│  - Trust Policy (repo-specific) │
└─────────────────────────────────┘
```

### Deployment Workflow
```
GitHub Push → GitHub Actions → AWS OIDC Auth → CDK Deploy → Application Stack
```

---

## Commands Reference

```bash
# View bootstrap stack
aws cloudformation describe-stacks \
  --stack-name UpBankLunchMoneySyncBootstrap

# View bootstrap stack outputs
aws cloudformation describe-stacks \
  --stack-name UpBankLunchMoneySyncBootstrap \
  --query 'Stacks[0].Outputs'

# Update bootstrap stack (if needed)
cdk deploy --app "python3 bootstrap_app.py"

# Remove bootstrap stack (cleanup)
cdk destroy --app "python3 bootstrap_app.py"
```

---

## Troubleshooting

### "Unable to assume role"
- Verify `AWS_ROLE_ARN` in GitHub secrets matches the output from Step 1
- Check trust policy includes your repository name

### "Secret not found"
- Verify secrets exist in AWS Secrets Manager
- Ensure ARNs are complete (copy-paste from Step 2)
- Check region matches

### Bootstrap deploy fails
```bash
# Ensure CDK is bootstrapped
cdk bootstrap

# Try again
cdk deploy --app "python3 bootstrap_app.py"
```

---

## Next Steps

1. ✅ Set up branch protection rules (optional)
2. ✅ Test with a real code change
3. ✅ Monitor CloudWatch logs
4. ✅ Read [DEPLOYMENT.md](DEPLOYMENT.md) for advanced topics

**Congratulations! 🎉** Your project now deploys automatically to AWS on every push to main!
