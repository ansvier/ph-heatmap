# HotMap Runner Bootstrap

The HotMap daily-scrape workflow runs on a single self-hosted GitHub
Actions runner on a Hetzner Cloud CX23 (~$5/mo). This file is the
runbook for setting up a fresh runner from zero — useful if the VM
dies, is migrated, or replaced.

## Server

- Provider: Hetzner Cloud
- Plan: CX23 (2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB transfer/mo) — ~$5/mo
- Region: Falkenstein (`fsn1`)
- OS: Ubuntu 26.04 LTS
- IP: 167.233.111.75
- SSH alias: `ssh hotmap` (configured locally via `~/.ssh/config`)
- SSH key: `~/.ssh/hotmap-hetzner` (backup in 1Password)

## Runner

- Name: `hotmap-runner-01`
- Labels: `self-hosted`, `linux`, `x64`, `hotmap`
- Working directory: `/home/runner/actions-runner/_work`
- systemd service: `hotmap-runner.service`
- Logs: `journalctl -u hotmap-runner.service -f`

To stop/start: `sudo systemctl stop hotmap-runner.service` / `start` / `restart`.

## Bootstrap steps (fresh VM from zero)

Provision a CX23 in Falkenstein via the [Hetzner Cloud Console](https://console.hetzner.cloud/),
attach the `hotmap-hetzner-runner` SSH key during creation, and note the IP. Then:

### 1. As root on the fresh VM

```bash
ssh -i ~/.ssh/hotmap-hetzner root@<IP>
```

```bash
export DEBIAN_FRONTEND=noninteractive

# OS patch + packages
apt-get update -q
apt-get upgrade -y -q -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"
apt-get install -y -q \
  python3 python3-venv python3-pip \
  git curl jq \
  ufw fail2ban unattended-upgrades \
  build-essential libssl-dev libcurl4-openssl-dev

# Create runner user with the same SSH key
adduser --disabled-password --gecos "" runner
mkdir -p /home/runner/.ssh
cp /root/.ssh/authorized_keys /home/runner/.ssh/authorized_keys
chown -R runner:runner /home/runner/.ssh
chmod 700 /home/runner/.ssh
chmod 600 /home/runner/.ssh/authorized_keys

# Sudo for runner (single-tenant VM — full sudo is acceptable)
cat > /etc/sudoers.d/runner-wide <<'EOF'
runner ALL=(ALL) NOPASSWD: ALL
EOF
chmod 440 /etc/sudoers.d/runner-wide
visudo -c -f /etc/sudoers.d/runner-wide

# Firewall: only SSH inbound
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw --force enable

# fail2ban (default sshd jail enabled by package)
systemctl enable --now fail2ban

# Unattended OS upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable unattended-upgrades

# SSH hardening: no password auth, no root login
cat > /etc/ssh/sshd_config.d/99-hotmap.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
sshd -t && systemctl reload ssh
```

**Verify before disconnecting** (in a second terminal):

```bash
ssh -i ~/.ssh/hotmap-hetzner runner@<IP> "whoami && hostname"   # → runner, hotmap-runner-01
ssh -i ~/.ssh/hotmap-hetzner root@<IP> "echo should fail"        # → Permission denied (expected)
```

### 2. As `runner` — install GitHub Actions runner

Get a registration token from
[github.com/ansvier/ph-heatmap/settings/actions/runners/new?os=linux&arch=x64](https://github.com/ansvier/ph-heatmap/settings/actions/runners/new?os=linux&arch=x64)
(valid for 1 hour). Then:

```bash
ssh hotmap   # uses the configured alias

# Download
cd ~
mkdir actions-runner && cd actions-runner
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
curl -sLo "actions-runner-linux-x64-$RUNNER_VERSION.tar.gz" \
  "https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/actions-runner-linux-x64-$RUNNER_VERSION.tar.gz"
tar xzf "actions-runner-linux-x64-$RUNNER_VERSION.tar.gz"

# Register
./config.sh \
  --url https://github.com/ansvier/ph-heatmap \
  --token PASTE_TOKEN_HERE \
  --name hotmap-runner-01 \
  --labels self-hosted,linux,x64,hotmap \
  --work _work \
  --unattended \
  --replace

# Install as systemd service. GH runner v2.335+ no longer ships svc.sh —
# we write the unit ourselves.
sudo tee /etc/systemd/system/hotmap-runner.service > /dev/null <<'UNIT'
[Unit]
Description=GitHub Actions Runner (ansvier/ph-heatmap, hotmap-runner-01)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=runner
Group=runner
WorkingDirectory=/home/runner/actions-runner
ExecStart=/home/runner/actions-runner/run.sh
Restart=always
RestartSec=10
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=5min
SuccessExitStatus=0 143

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable hotmap-runner.service
sudo systemctl start hotmap-runner.service
```

Verify:

```bash
sudo systemctl status hotmap-runner.service
journalctl -u hotmap-runner.service -n 20
# Expect: "Listening for Jobs" in the last few lines.
```

Then trigger a manual workflow_dispatch from your local Mac to smoke test:

```bash
gh workflow run daily-scrape.yml --ref main
RUN_ID=$(gh run list --workflow daily-scrape.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID"
```

Look for `wrote 870+ performer pages` in the logs. <800 means PH is throttling
the IP — see Plan B below.

## Plan B: residential proxy

If PH starts returning Cloudflare challenges to the Hetzner ASN and per-profile
scrape success drops below 80%:

1. Sign up at a residential proxy provider:
   - [Smartproxy Residential](https://smartproxy.com/residential-proxies) — ~$12.50/mo for 1 GB
   - [DataImpulse](https://dataimpulse.com/) — pay-as-you-go, ~$1/GB
2. From the dashboard get: `endpoint:port` (e.g., `gate.smartproxy.com:7000`), `username`, `password`.
3. SSH into the runner:
   ```bash
   ssh hotmap
   sudo systemctl edit hotmap-runner.service
   ```
4. Paste in the editor:
   ```ini
   [Service]
   Environment="HTTPS_PROXY=http://USER:PASS@gate.smartproxy.com:7000"
   Environment="HTTP_PROXY=http://USER:PASS@gate.smartproxy.com:7000"
   ```
5. Save and reload:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart hotmap-runner.service
   ```
6. `curl-cffi` honours `HTTPS_PROXY` transparently — no code changes needed.

To disable later: `sudo systemctl edit hotmap-runner.service` and remove the
Environment lines (or replace with empty values).

## Day-to-day maintenance

Negligible. `unattended-upgrades` handles security patches nightly. Manual
check every ~6 months:

```bash
ssh hotmap
sudo apt update && sudo apt list --upgradable
sudo systemctl status hotmap-runner.service
df -h /
free -h
```

If the runner falls offline (visible in
[GH Settings → Runners](https://github.com/ansvier/ph-heatmap/settings/actions/runners)):

```bash
ssh hotmap
sudo journalctl -u hotmap-runner.service -n 100
sudo systemctl restart hotmap-runner.service
```

## Cost

- Hetzner CX23: ~$5/mo (~$60/year)
- Domain: ~$15/year
- GitHub Actions (public repo + self-hosted runner): $0
- Cloudflare Pages + Worker (free tier): $0
- **Total: ~$75/year** (or $87/year if Plan B residential proxy gets enabled)
