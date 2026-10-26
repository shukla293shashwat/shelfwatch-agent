#!/usr/bin/env bash
# Run from the project root in AWS CloudShell after account activation.
set -euo pipefail
export AWS_PAGER=''
project_root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$project_root"
region=${AWS_REGION:-ap-south-1}
stack=shelfwatch-demo
state=deployment-state.json
if [ -e "$state" ]; then
  echo 'Existing deployment state found. Review or clean up that deployment first.' >&2
  exit 1
fi
# No resource is created unless the current account satisfies the zero-charge gate.
aws freetier get-account-plan-state --region us-east-1 --output json > /tmp/shelfwatch-plan.json
python3 deploy/aws/check_free_plan.py < /tmp/shelfwatch-plan.json
account=$(aws sts get-caller-identity --query Account --output text)
suffix=$(date +%s)
bucket="shelfwatch-$account-$suffix"
parameter="/shelfwatch/$suffix/access-code"
python3 - "$region" "$stack" "$bucket" "$parameter" <<'PY'
import json,sys
from pathlib import Path
Path('deployment-state.json').write_text(json.dumps(dict(zip(('region','stack','bucket','token_parameter'),sys.argv[1:])),indent=2))
PY
if [ "$region" = us-east-1 ]; then
  aws s3api create-bucket --bucket "$bucket" --region "$region" >/dev/null
else
  aws s3api create-bucket --bucket "$bucket" --region "$region" --create-bucket-configuration "LocationConstraint=$region" >/dev/null
fi
aws s3api put-public-access-block --bucket "$bucket" --public-access-block-configuration 'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'
aws s3api put-bucket-encryption --bucket "$bucket" --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
access_code=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
aws ssm put-parameter --name "$parameter" --type SecureString --value "$access_code" --region "$region" >/dev/null
unset access_code
artifact="/tmp/shelfwatch-source-$suffix.zip"
python3 scripts/package_release.py --runtime-only --output "$artifact"
digest=$(sha256sum "$artifact" | cut -d ' ' -f 1)
aws s3 cp "$artifact" "s3://$bucket/source.zip" --region "$region" --sse AES256
python3 deploy/aws/build_template.py
aws cloudformation validate-template --template-body file://deploy/aws/template.json --region "$region" >/dev/null
aws cloudformation deploy --stack-name "$stack" --region "$region" --template-file deploy/aws/template.json --capabilities CAPABILITY_IAM --parameter-overrides "SourceBucket=$bucket" SourceKey=source.zip "SourceSha256=$digest" "TokenParameter=$parameter" InstanceType=t3.small DemoLifetimeHours=72
aws cloudformation describe-stacks --stack-name "$stack" --region "$region" --query 'Stacks[0].Outputs' --output table
echo 'The private demo access code is in the SSM SecureString parameter recorded in deployment-state.json.'
echo 'Retrieve it privately in the AWS console; do not paste it into chat or commit it.'
echo 'The instance terminates after 72 hours. Run the cleanup script to remove remaining resources.'
