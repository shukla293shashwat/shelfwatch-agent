# AWS delivery

This folder contains deployment code, not a claim that ShelfWatch is already running on AWS. Account sign-in and activation must finish before deployment can be verified.

## Zero-charge requirement

The owner chose a ₹0 spending limit. `deploy.sh` checks the authenticated account with the Free Tier API before creating any resources. It stops unless the plan is `FREE`, its status is `ACTIVE`, at least USD 5 of Free-plan credits remain, and its expiration is more than a day away. It never calls the upgrade API. If that check fails or the API is unavailable, stop and resolve the account status; do not substitute a Paid plan.

AWS describes its Free plan as incurring no charges unless upgraded: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html

The API fields used by the gate are documented here: https://docs.aws.amazon.com/cli/latest/reference/freetier/get-account-plan-state.html

## What gets deployed

- One disposable Amazon Linux 2023 EC2 `t3.small` instance running the actual OpenCV 5/FastAPI container. Core vision runs on AWS, rather than merely linking to an AWS service.
- A private, encrypted S3 source archive, verified by SHA-256 before installation.
- A selected-region SSM SecureString for the access code. The secret is not embedded in the template or committed to the repository.
- HTTPS through Caddy and a temporary `sslip.io` hostname based on the instance's public IP. This depends on external DNS and ACME availability; the stack is not signalled ready unless HTTPS health responds.
- Only ports 80 and 443 are publicly reachable. The Python port binds to loopback; there is no public SSH port.
- IMDSv2, a scoped instance policy, short-retention CloudWatch application logs, a read-only container filesystem, CPU/memory limits, and a Docker volume for SQLite.
- Automatic instance termination after 72 hours. This makes the live URL temporary; plan an appropriate judging window. Cleanup also removes the source bucket, secret, IAM, networking and logs.

This is a small demo deployment, not a high-availability production system. The instance's state volume is deleted on termination. Export any audit records you need before deleting it. The Caddy and Python image tags are not digest-pinned yet; record the resolved image digests for the final deployment evidence.

## Deploy using CloudShell

1. Finish AWS signup/sign-in in the official console. Choose the Free account plan and complete identity verification yourself.
2. Open CloudShell in the console. If CloudShell or the required services are unavailable under your account, stop rather than upgrade.
3. Upload and extract the current project ZIP using CloudShell's file-upload control. Enter the extracted project folder.
4. Run:

```sh
bash deploy/aws/deploy.sh
```

The default region is Mumbai (`ap-south-1`). Set `AWS_REGION` to another supported region before running if needed. Activation, regional availability, IAM permissions, image pulls and HTTPS certificate issuance still require verification in the actual account.

The CloudFormation stack signals success only after the app answers through HTTPS. Save the stack outputs, `/health` response, a real analysis response and CloudWatch logs as deployment evidence. The code alone does not satisfy the hackathon's AWS requirement.

The access code is stored in the SSM parameter named in `deployment-state.json`. Retrieve it privately from Parameter Store and provide it to judges through an appropriate private submission field. Do not publish AWS access keys or the root password.

## Check after deployment

1. Open the `DemoUrl` stack output and check that HTTPS is valid.
2. Confirm `/health` reports OpenCV 5 and `auth_required: true`.
3. Confirm an analysis request without the demo code returns 401.
4. Run the generated sample and the real-photo development example; inspect the localized boxes and decision trace.
5. Approve a draft and verify `/orders` records approval. No supplier order is transmitted.
6. Inspect `/metrics` and the CloudWatch log group. Logs contain request metadata, not photos or access codes.
7. Record the actual AWS resource IDs, region, resolved image digests, time and source archive hash in the technical report.

## Cleanup

From the same extracted project folder in CloudShell:

```sh
bash deploy/aws/cleanup.sh
```

It validates the recorded bucket/account prefix and asks for `DELETE` before removing resources. Keep `deployment-state.json` until cleanup finishes. Source uploads, secrets or resources left behind after a failed attempt still need cleanup. Do not assume that terminating only the EC2 instance removes everything.

## Local CLI alternative to CloudShell

If CloudShell is unavailable, use the official AWS CLI v2. Its `aws login` command obtains temporary credentials through your browser; do not create root access keys or share a password.

```powershell
aws login --profile shelfwatch-hackathon --region ap-south-1
.\.venv\Scripts\python.exe deploy/aws/deploy.py --profile shelfwatch-hackathon --region ap-south-1
```

The Python driver applies the same Free-plan gate and makes an EC2 read-only probe before creating anything. `NOT_STARTED` or `OptInRequired` means that the required access has not been confirmed; wait for AWS activation or resolve verification through AWS support. Never change to a Paid plan as a workaround for the zero-charge requirement.
