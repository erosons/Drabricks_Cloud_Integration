#!/bin/bash
set -e

# Log output
exec > >(tee /var/log/runner-setup.log)
exec 2>&1

echo "Starting GitHub Actions Runner setup..."

# Update system
apt-get update
apt-get upgrade -y

# Install dependencies
apt-get install -y \
  curl \
  jq \
  git \
  wget \
  unzip \
  build-essential \
  libssl-dev \
  ca-certificates \
  apt-transport-https \
  software-properties-common

# Install Docker (common for CI/CD)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker ubuntu

# Install Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Create runner directory
cd /home/ubuntu
mkdir -p actions-runner
cd actions-runner

# Get latest runner version
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r '.tag_name' | sed 's/v//')

# Download and extract runner
curl -o actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz -L \
  https://github.com/actions/runner/releases/download/v$${RUNNER_VERSION}/actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz

tar xzf ./actions-runner-linux-x64-$${RUNNER_VERSION}.tar.gz

# Set ownership
chown -R ubuntu:ubuntu /home/ubuntu/actions-runner

# Configure runner as ubuntu user
su - ubuntu -c "cd /home/ubuntu/actions-runner && ./config.sh \
  --url ${github_url} \
  --token ${runner_token} \
  --name ${runner_name} \
  --labels ${runner_labels} \
  --runnergroup ${runner_group} \
  --work _work \
  --unattended \
  --replace"

# Install as service
cd /home/ubuntu/actions-runner
./svc.sh install ubuntu
./svc.sh start

echo "GitHub Actions Runner setup completed successfully!"
echo "Runner name: ${runner_name}"
echo "Labels: ${runner_labels}"
echo "Status:"
./svc.sh status