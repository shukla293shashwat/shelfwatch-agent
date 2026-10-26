#!/usr/bin/env bash
# Remove only the resources listed in this project's recorded deployment state.
set -euo pipefail
export AWS_PAGER=''
cd "$(dirname "$0")/../.."
[ -f deployment-state.json ] || { echo 'No deployment-state.json found.' >&2; exit 1; }
read -r region stack bucket parameter < <(python3 -c "import json; s=json.load(open('deployment-state.json')); print(s['region'],s['stack'],s['bucket'],s['token_parameter'])")
account=$(aws sts get-caller-identity --query Account --output text)
case "$bucket" in "shelfwatch-$account-"*) ;; *) echo 'Bucket is not the recorded project bucket for this AWS account.' >&2; exit 1;; esac
[ "$stack" = shelfwatch-demo ] || { echo 'Unexpected stack name.' >&2; exit 1; }
case "$parameter" in /shelfwatch/*/access-code) ;; *) echo 'Unexpected parameter path.' >&2; exit 1;; esac
printf 'Delete recorded stack %s, its source bucket, and its demo secret? Type DELETE: ' "$stack"
read -r confirmation
[ "$confirmation" = DELETE ] || exit 0
if aws cloudformation describe-stacks --stack-name "$stack" --region "$region" >/dev/null 2>&1; then
  aws cloudformation delete-stack --stack-name "$stack" --region "$region"
  aws cloudformation wait stack-delete-complete --stack-name "$stack" --region "$region"
fi
aws s3 rb "s3://$bucket" --force --region "$region"
aws ssm delete-parameter --name "$parameter" --region "$region"
mv deployment-state.json deployment-state.cleaned.json
echo 'Recorded project resources removed. Check Billing and the resource console for any unrelated resources.'
