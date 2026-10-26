#!/usr/bin/env bash
# Runs as EC2 user data. The access code is fetched privately from SSM.
set -euo pipefail
export AWS_DEFAULT_REGION='${AWS::Region}'
signal_status() {
  aws cloudformation signal-resource --stack-name '${AWS::StackName}' --logical-resource-id Server --unique-id shelfwatch-bootstrap --status "$1" || true
}
trap 'signal_status FAILURE' ERR

dnf install -y docker unzip awscli2
systemctl enable --now docker
mkdir -p /opt/shelfwatch/source
aws s3 cp 's3://${SourceBucket}/${SourceKey}' /opt/shelfwatch/source.zip
printf '%s  %s\n' '${SourceSha256}' /opt/shelfwatch/source.zip | sha256sum --check --status
unzip -q /opt/shelfwatch/source.zip -d /opt/shelfwatch/source
cd /opt/shelfwatch/source
docker build -t shelfwatch:2 .

# This script is also used after an instance reboot. No secret appears in user data.
cat > /opt/shelfwatch/start.sh <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
export AWS_DEFAULT_REGION='${AWS::Region}'
umask 077
access_code=$(aws ssm get-parameter --name '${TokenParameter}' --with-decryption --query Parameter.Value --output text)
printf 'HOST=0.0.0.0\nPORT=8000\nSHELFWATCH_PUBLIC=1\nSHELFWATCH_STATE_DIR=/data\nSHELFWATCH_TOKEN=%s\n' "$access_code" > /opt/shelfwatch/runtime.env
unset access_code
metadata_token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
public_ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $metadata_token" http://169.254.169.254/latest/meta-data/public-ipv4)
cat > /opt/shelfwatch/Caddyfile <<CADDY
https://$public_ip.sslip.io {
  encode gzip
  request_body {
    max_size 26MB
  }
  reverse_proxy 127.0.0.1:8000
}
CADDY
docker rm -f shelfwatch shelfwatch-proxy >/dev/null 2>&1 || true
docker run -d --name shelfwatch --restart unless-stopped --read-only --tmpfs /tmp:size=64m --pids-limit 128 --cpus 1 --memory 1200m --env-file /opt/shelfwatch/runtime.env -v shelfwatch-state:/data -p 127.0.0.1:8000:8000 --log-driver awslogs --log-opt awslogs-region='${AWS::Region}' --log-opt awslogs-group='${AppLogs}' --log-opt awslogs-stream=api shelfwatch:2
docker run -d --name shelfwatch-proxy --restart unless-stopped --network host -v /opt/shelfwatch/Caddyfile:/etc/caddy/Caddyfile:ro -v shelfwatch-caddy-data:/data -v shelfwatch-caddy-config:/config --log-driver json-file --log-opt max-size=10m --log-opt max-file=2 caddy:2.10.2-alpine
RUN
chmod 700 /opt/shelfwatch/start.sh
cat > /etc/systemd/system/shelfwatch.service <<'UNIT'
[Unit]
Description=ShelfWatch demo and HTTPS proxy
Requires=docker.service
After=docker.service network-online.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/shelfwatch/start.sh
ExecStop=-/usr/bin/docker stop shelfwatch shelfwatch-proxy
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now shelfwatch
metadata_token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
public_ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $metadata_token" http://169.254.169.254/latest/meta-data/public-ipv4)
ready=0
for attempt in $(seq 1 60); do
  if curl -fsS "https://$public_ip.sslip.io/health" >/dev/null; then ready=1; break; fi
  sleep 10
done
[ "$ready" = 1 ]
# The disposable demo terminates after its declared lifetime; cleanup removes the rest.
systemd-run --unit shelfwatch-expiry --on-active='${DemoLifetimeHours}h' /sbin/shutdown -h now
signal_status SUCCESS
