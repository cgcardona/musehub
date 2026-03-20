#!/usr/bin/env bash
# Run this locally (after installing AWS CLI and running `aws configure`).
# Creates an EC2 t3.small, security group, key pair, and Elastic IP for musehub.ai.
#
# Prerequisites:
#   brew install awscli
#   aws configure  (enter your Access Key ID, Secret, region=us-east-1, output=json)
#
# Usage:
#   chmod +x deploy/aws-provision.sh
#   ./deploy/aws-provision.sh

set -euo pipefail

# Suppress AWS CLI pager entirely — prevents the script from blocking on `less`
export AWS_PAGER=""

REGION="us-east-1"
AMI_ID="ami-0c7217cdde317cfec"   # Ubuntu 22.04 LTS (us-east-1, 2024)
INSTANCE_TYPE="t3.small"
KEY_NAME="musehub-key"
SG_NAME="musehub-sg"
SG_ID="sg-05815872537fcfe76"     # Already created — skip re-creation
INSTANCE_NAME="musehub-prod"

# ── Key pair ──────────────────────────────────────────────────────────────────
if [ -f ~/.ssh/${KEY_NAME}.pem ]; then
    echo "==> Key pair already exists at ~/.ssh/${KEY_NAME}.pem, skipping"
else
    echo "==> Creating key pair: $KEY_NAME"
    aws ec2 create-key-pair \
        --region "$REGION" \
        --key-name "$KEY_NAME" \
        --query 'KeyMaterial' \
        --output text > ~/.ssh/${KEY_NAME}.pem
    chmod 400 ~/.ssh/${KEY_NAME}.pem
    echo "    Key saved to ~/.ssh/${KEY_NAME}.pem"
fi

# ── Current IP ────────────────────────────────────────────────────────────────
echo "==> Getting your current public IP..."
MY_IP=$(curl -s https://checkip.amazonaws.com)
echo "    Your IP: $MY_IP"

# ── Security group ────────────────────────────────────────────────────────────
echo "==> Using existing security group: $SG_ID"

# ── Inbound rules (idempotent — ignore duplicate-rule errors) ─────────────────
echo "==> Adding inbound rules (SSH / HTTP / HTTPS)..."

add_rule() {
    local port=$1 cidr=$2
    aws ec2 authorize-security-group-ingress \
        --region "$REGION" \
        --group-id "$SG_ID" \
        --protocol tcp --port "$port" --cidr "$cidr" \
        --output text > /dev/null 2>&1 \
    && echo "    Port $port ($cidr) — added" \
    || echo "    Port $port ($cidr) — already exists, skipping"
}

add_rule 22  "${MY_IP}/32"
add_rule 80  "0.0.0.0/0"
add_rule 443 "0.0.0.0/0"

# ── EC2 instance ──────────────────────────────────────────────────────────────
# Check if instance already exists
EXISTING=$(aws ec2 describe-instances \
    --region "$REGION" \
    --filters "Name=tag:Name,Values=$INSTANCE_NAME" "Name=instance-state-name,Values=pending,running,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' \
    --output text)

if [ "$EXISTING" != "None" ] && [ -n "$EXISTING" ]; then
    echo "==> Instance already exists: $EXISTING"
    INSTANCE_ID="$EXISTING"
else
    echo "==> Launching EC2 instance..."
    INSTANCE_ID=$(aws ec2 run-instances \
        --region "$REGION" \
        --image-id "$AMI_ID" \
        --instance-type "$INSTANCE_TYPE" \
        --key-name "$KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":20,"VolumeType":"gp3","DeleteOnTermination":true}}]' \
        --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
        --query 'Instances[0].InstanceId' \
        --output text)
    echo "    Instance ID: $INSTANCE_ID"
fi

echo "==> Waiting for instance to be running..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
echo "    Instance is running"

# ── Elastic IP ────────────────────────────────────────────────────────────────
# Check if already associated
EXISTING_EIP=$(aws ec2 describe-addresses \
    --region "$REGION" \
    --filters "Name=instance-id,Values=$INSTANCE_ID" \
    --query 'Addresses[0].PublicIp' \
    --output text)

if [ "$EXISTING_EIP" != "None" ] && [ -n "$EXISTING_EIP" ]; then
    echo "==> Elastic IP already associated: $EXISTING_EIP"
    PUBLIC_IP="$EXISTING_EIP"
else
    echo "==> Allocating Elastic IP..."
    ALLOC_ID=$(aws ec2 allocate-address \
        --region "$REGION" \
        --domain vpc \
        --query 'AllocationId' \
        --output text)
    echo "    Allocation ID: $ALLOC_ID"

    echo "==> Associating Elastic IP with instance..."
    aws ec2 associate-address \
        --region "$REGION" \
        --instance-id "$INSTANCE_ID" \
        --allocation-id "$ALLOC_ID" \
        --output text > /dev/null

    PUBLIC_IP=$(aws ec2 describe-addresses \
        --region "$REGION" \
        --allocation-ids "$ALLOC_ID" \
        --query 'Addresses[0].PublicIp' \
        --output text)
fi

echo ""
echo "============================================================"
echo "  DONE. Your EC2 instance is ready."
echo "============================================================"
echo "  Instance ID : $INSTANCE_ID"
echo "  Elastic IP  : $PUBLIC_IP"
echo "  Key file    : ~/.ssh/${KEY_NAME}.pem"
echo ""
echo "  DNS records to add at Namecheap (Advanced DNS tab):"
echo "  ┌──────────┬──────────┬────────────────┬───────────┐"
echo "  │ Type     │ Host     │ Value          │ TTL       │"
echo "  ├──────────┼──────────┼────────────────┼───────────┤"
echo "  │ A Record │ @        │ $PUBLIC_IP     │ Automatic │"
echo "  │ A Record │ www      │ $PUBLIC_IP     │ Automatic │"
echo "  └──────────┴──────────┴────────────────┴───────────┘"
echo "  Also DELETE the existing TXT record (the SPF one)."
echo ""
echo "  Verify propagation: dig musehub.ai +short"
echo ""
echo "  SSH into the server:"
echo "    ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$PUBLIC_IP"
echo ""
echo "  Then run: bash /opt/musehub/deploy/setup-ec2.sh"
echo "============================================================"
