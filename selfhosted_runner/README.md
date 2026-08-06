# GitHub Actions Self-Hosted Runner - Terraform

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **GitHub Personal Access Token** with `repo` and `admin:org` scopes
   - Create at: https://github.com/settings/tokens
3. **Terraform** installed (>= 1.0)
4. **SSH Key** for EC2 access (optional)

## Setup

### 1. Create SSH Key (optional, for debugging)
```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/github-runner-key
```

### 2. Set GitHub Token
```bash
export TF_VAR_github_token="ghp_your_token_here"
```

### 3. Initialize Terraform
```bash
terraform init
```

### 4. Review Plan
```bash
terraform plan
```

### 5. Apply
```bash
terraform apply
```

### 6. Verify Runners
Go to: `https://github.com/YOURORG/YOURREPO/settings/actions/runners`

## Usage in Workflows
```yaml
jobs:
  build:
    runs-on: [self-hosted, production, terraform-managed]
    steps:
      - uses: actions/checkout@v3
      - run: echo "Running on self-hosted runner!"
```

## Scaling

To add more runners:
```hcl
# In terraform.tfvars
runner_count = 5
```

Then run:
```bash
terraform apply
```

## Cleanup
```bash
terraform destroy
```

## Troubleshooting

### SSH into runner:
```bash
ssh -i ~/.ssh/github-runner-key ubuntu@<RUNNER_IP>
```

### Check runner logs:
```bash
tail -f /var/log/runner-setup.log
sudo journalctl -u actions.runner.* -f
```

### Check runner status:
```bash
cd /home/ubuntu/actions-runner
sudo ./svc.sh status
```