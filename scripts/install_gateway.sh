#!/usr/bin/env bash
# Run from inspected new project directory, as sudo. Never edits existing service config.
set -euo pipefail
project=$(pwd)
if [ "$(id -u)" != 0 ]; then echo 'Run with sudo from the project directory'; exit 1; fi
if ! id aiops-gateway >/dev/null 2>&1; then useradd --system --home-dir /var/lib/aiops-gateway --shell /usr/sbin/nologin aiops-gateway; fi
install -d -m 755 /opt/aiops-gateway /opt/aiops-gateway/config
install -d -o aiops-gateway -g aiops-gateway -m 700 /var/lib/aiops-gateway
# Backup this project's own files before an update.
if [ -f /etc/aiops-gateway.env ]; then
 install -d -m 700 /opt/aiops-gateway/backups
 stamp=$(date -u +%Y%m%dT%H%M%SZ)
 cp -a /etc/aiops-gateway.env "/opt/aiops-gateway/backups/env-$stamp"
 cp -a /opt/aiops-gateway/config/gateway.json "/opt/aiops-gateway/backups/config-$stamp.json"
fi
cp -R diagnostic_gateway /opt/aiops-gateway/
cp config/gateway.json /opt/aiops-gateway/config/gateway.json
python3 -m venv /opt/aiops-gateway/venv
/opt/aiops-gateway/venv/bin/pip install -r diagnostic_gateway/requirements.txt
python3 - <<'PY'
import os
from pathlib import Path
values=dict(line.split('=',1) for line in Path('.env').read_text().splitlines() if line and not line.startswith('#'))
p=Path('/etc/aiops-gateway.env')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:
 for k in ['GATEWAY_TOKEN','GATEWAY_APPROVAL_SECRET']:f.write(k+'='+values[k]+'\n')
PY
chown -R root:root /opt/aiops-gateway
install -m 644 deploy/aiops-gateway.service /etc/systemd/system/aiops-gateway.service
systemctl daemon-reload
systemctl enable --now aiops-gateway.service
systemctl restart aiops-gateway.service
systemctl is-active aiops-gateway.service
