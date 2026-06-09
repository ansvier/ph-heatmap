# Runner Migration to Hetzner — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Note for the user:** This plan mixes commands you (the user) run on your local Mac, on the new Hetzner VM via SSH, and in browser tabs (Hetzner Cloud Console + GitHub Settings). Each step is labelled `(local)`, `(VM)`, or `(browser)` so you know where to execute it.

**Goal:** Move daily-scrape from the Mac mini self-hosted runner to a $4/mo Hetzner Cloud VM that runs 24/7 without user attention.

**Architecture:** Hetzner CX22 (Ubuntu 24.04 LTS) running a GitHub Actions self-hosted runner as a systemd service. Single-line workflow YAML cutover after smoke test confirms PH lets the datacenter IP scrape. Existing TLS-fingerprint fallback in `scraper.py` provides PH-blocking resilience without proxy.

**Tech Stack:** Hetzner Cloud (provisioning), Ubuntu 24.04 LTS, systemd, GitHub Actions runner (linux-x64), ufw + fail2ban + unattended-upgrades (hardening). No code changes; one workflow YAML edit.

**Spec:** `docs/superpowers/specs/2026-06-09-runner-migration-design.md`

---

## File map

| Path | Purpose | Tasks |
|---|---|---|
| `~/.ssh/hotmap-hetzner` and `~/.ssh/hotmap-hetzner.pub` (local) | New SSH keypair for the Hetzner VM | Task 1 |
| `docs/runner-bootstrap.md` (in repo) | Runbook documenting Hetzner setup, runner install, hardening, Plan B proxy config | Tasks 1, 8 |
| `.github/workflows/daily-scrape.yml` | One-line `runs-on:` change after smoke test passes | Task 6 |
| `README.md` | "Hosting" subsection mentioning Hetzner | Task 7 |
| **Hetzner Cloud Console** (browser) | Provision CX22 VM, attach SSH key | Task 2 |
| **GitHub repo Settings → Actions → Runners** (browser) | Get registration token; later remove Mac mini runner | Tasks 4, 7 |
| **VM at `/home/runner/`** | GitHub Actions runner binaries + cached venv | Tasks 3, 4 |

No Python code changes. No new dependencies.

---

### Task 1: Prep local — generate SSH key + scaffold runbook

**Files:**
- Create: `~/.ssh/hotmap-hetzner`, `~/.ssh/hotmap-hetzner.pub` (local Mac)
- Create: `docs/runner-bootstrap.md` (in repo)

- [ ] **Step 1.1 (local): Generate a fresh SSH keypair for the Hetzner VM**

Open Terminal on your Mac:

```bash
ssh-keygen -t ed25519 -C "hotmap-hetzner-runner" -f ~/.ssh/hotmap-hetzner -N ""
```

Expected: Two files created. `~/.ssh/hotmap-hetzner` (private, mode 600) and `~/.ssh/hotmap-hetzner.pub` (public).

- [ ] **Step 1.2 (local): Back up the private key**

Copy the contents of `~/.ssh/hotmap-hetzner` (private key) into your password manager (1Password / Apple Keychain / Bitwarden). Label it "HotMap Hetzner runner SSH key". If your Mac dies, this key is the only way to SSH back in without using Hetzner's web console rescue mode.

```bash
cat ~/.ssh/hotmap-hetzner | pbcopy
# Paste into 1Password as a Secure Note titled "HotMap Hetzner SSH key"
```

- [ ] **Step 1.3 (local): Add an SSH config entry for convenience**

Edit `~/.ssh/config` (create if missing):

```bash
cat >> ~/.ssh/config <<'EOF'

Host hotmap
  HostName <PASTE_IP_AFTER_TASK_2>
  User runner
  IdentityFile ~/.ssh/hotmap-hetzner
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

We'll fill in `<PASTE_IP_AFTER_TASK_2>` once Hetzner gives us the VM's IP.

- [ ] **Step 1.4: Scaffold the runbook file**

```bash
cd /Users/ansvier/ph-heatmap
mkdir -p docs
cat > docs/runner-bootstrap.md <<'EOF'
# HotMap Runner Bootstrap

The HotMap daily-scrape workflow runs on a single self-hosted GitHub
Actions runner on a Hetzner Cloud CX22 (~$4/mo). This file is the
runbook for setting up a fresh runner from zero — useful if the VM
dies, is migrated, or replaced.

Fill in the sections below as Tasks 2–7 of the migration plan are
completed.

## Server

- Provider: Hetzner Cloud
- Plan: CX22 (1 vCPU, 2 GB RAM, 40 GB SSD, 20 TB transfer)
- Region: Falkenstein (`fsn1`)
- OS: Ubuntu 24.04 LTS
- IP: (filled in after Task 2)
- SSH alias: `ssh hotmap` (configured locally via `~/.ssh/config`)

## Bootstrap steps

(filled in by Task 8 with the verified commands from Tasks 3–4)

## Plan B: residential proxy

If PH blocks the Hetzner datacenter IP and individual profile scrapes
fail >20% of the time, add a residential proxy. No code changes needed
— just an env var in the runner service.

(filled in by Task 8)
EOF
```

- [ ] **Step 1.5: Commit the scaffold**

```bash
git add docs/runner-bootstrap.md
git commit -m "docs: scaffold runner-bootstrap runbook (to be filled by migration)"
```

---

### Task 2: Provision Hetzner CX22

**Files:** None (browser-side actions).

This task is mostly clicking in the Hetzner Cloud Console. No code changes.

- [ ] **Step 2.1 (browser): Sign in to Hetzner Cloud**

Open `https://console.hetzner.cloud/`. If you don't have an account yet, create one. You'll need to:
1. Provide email + password
2. Verify email
3. Add billing info (credit card / SEPA / PayPal — try card first)
4. Pass identity verification if asked (Hetzner sometimes requires a quick ID check for first-time customers; takes a few minutes)

- [ ] **Step 2.2 (browser): Create a new project**

In the top-left, click "Projects" → "New Project". Name it `hotmap`. Click Create.

- [ ] **Step 2.3 (browser): Upload your SSH public key**

In the `hotmap` project sidebar: Security → SSH Keys → Add SSH Key.

Paste the contents of your public key. On Mac:

```bash
cat ~/.ssh/hotmap-hetzner.pub | pbcopy
```

Then paste in the textbox. Name it `hotmap-hetzner-runner`. Add Key.

- [ ] **Step 2.4 (browser): Create the server**

In the `hotmap` project sidebar: Servers → Add Server.

Settings:
- **Location:** Falkenstein (Germany) — `fsn1`
- **Image:** Ubuntu 24.04
- **Type:** Shared vCPU → `CX22` (€3.79/mo)
- **Networking:** IPv4 only (default; saves ~€0.50/mo if you skip IPv6)
- **SSH keys:** check the `hotmap-hetzner-runner` you just added
- **Volume / firewall / backups:** skip all (we'll configure ufw on-box)
- **Name:** `hotmap-runner-01`

Click "Create & Buy now".

After ~30 seconds the server shows up with a public IPv4 address. Copy that IP.

- [ ] **Step 2.5 (local): Update SSH config with the IP**

```bash
# Replace <PASTE_IP_AFTER_TASK_2> in ~/.ssh/config with the actual IP.
# On Mac:
HETZNER_IP="REPLACE_ME"   # paste the IP from Hetzner console
sed -i '' "s|<PASTE_IP_AFTER_TASK_2>|$HETZNER_IP|" ~/.ssh/config
```

- [ ] **Step 2.6 (local): Verify SSH access as root first**

The newly-provisioned VM only has `root` access for the first login. Test:

```bash
ssh -i ~/.ssh/hotmap-hetzner -o StrictHostKeyChecking=accept-new root@$HETZNER_IP "echo 'hello from hetzner' && uname -a && cat /etc/os-release | head -2"
```

Expected output: `hello from hetzner` followed by `Linux hotmap-runner-01 ... aarch64 GNU/Linux` and `Ubuntu 24.04`.

If you get "Permission denied (publickey)", the SSH key isn't attached to the server. Go back to Step 2.4 and ensure the key was checked.

- [ ] **Step 2.7 (local): Record the IP in the runbook**

```bash
cd /Users/ansvier/ph-heatmap
sed -i '' "s|IP: (filled in after Task 2)|IP: $HETZNER_IP|" docs/runner-bootstrap.md
git add docs/runner-bootstrap.md
git commit -m "docs: record Hetzner runner IP in bootstrap runbook"
```

---

### Task 3: Bootstrap server — OS hardening + runner user

**Files:** None on local; all changes on the VM via SSH.

- [ ] **Step 3.1 (local): SSH in as root**

```bash
ssh -i ~/.ssh/hotmap-hetzner root@$HETZNER_IP
```

You're now on the VM as root. All subsequent steps in this task run on the VM unless marked `(local)`.

- [ ] **Step 3.2 (VM): Update OS packages**

```bash
apt-get update && apt-get upgrade -y
```

Takes ~1 minute. Don't worry about kernel-upgrade prompts; if any appear, default-Enter is fine.

- [ ] **Step 3.3 (VM): Install required packages**

```bash
apt-get install -y \
  python3 python3-venv python3-pip \
  git curl jq \
  ufw fail2ban unattended-upgrades \
  build-essential libssl-dev libcurl4-openssl-dev
```

`build-essential` and `libcurl4-openssl-dev` are required for `curl-cffi` to compile its native extension.

- [ ] **Step 3.4 (VM): Create the unprivileged `runner` user**

```bash
adduser --disabled-password --gecos "" runner
mkdir -p /home/runner/.ssh
cp /root/.ssh/authorized_keys /home/runner/.ssh/authorized_keys
chown -R runner:runner /home/runner/.ssh
chmod 700 /home/runner/.ssh
chmod 600 /home/runner/.ssh/authorized_keys
```

This creates a user named `runner` with no password (key-only login) and copies the SSH key you uploaded so you can SSH as `runner` directly.

- [ ] **Step 3.5 (VM): Grant `runner` passwordless sudo (only for the runner-install commands)**

We need this briefly to install the systemd service in Task 4 (`./svc.sh install` writes to `/etc/systemd/system/`).

```bash
echo "runner ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /home/runner/actions-runner/svc.sh" > /etc/sudoers.d/runner
chmod 440 /etc/sudoers.d/runner
visudo -c -f /etc/sudoers.d/runner
```

The `visudo -c` validates syntax. Expected: `/etc/sudoers.d/runner: parsed OK`.

- [ ] **Step 3.6 (VM): Configure firewall**

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw --force enable
ufw status verbose
```

Expected: `Status: active` with rules listing SSH allow. No other inbound ports are exposed — GitHub Actions runner connects OUT to GitHub, never accepts inbound.

- [ ] **Step 3.7 (VM): Configure fail2ban**

The default Ubuntu install enables the `sshd` jail automatically. Just verify:

```bash
systemctl enable --now fail2ban
fail2ban-client status sshd
```

Expected: `Status for the jail: sshd` with `Currently failed: 0`, `Total failed: 0`, etc.

- [ ] **Step 3.8 (VM): Enable unattended-upgrades**

```bash
dpkg-reconfigure -plow unattended-upgrades
```

When prompted "Automatically download and install stable updates?", select **Yes**.

Verify the config:

```bash
cat /etc/apt/apt.conf.d/20auto-upgrades
```

Expected output:
```
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
```

- [ ] **Step 3.9 (VM): Harden SSH config**

```bash
cat > /etc/ssh/sshd_config.d/99-hotmap.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF

# Validate config syntax before restarting
sshd -t && echo "OK"
```

Expected: `OK`.

- [ ] **Step 3.10 (VM): Restart SSH (carefully)**

**Important**: Before restarting SSH, open a SECOND terminal on your Mac and SSH in as `runner` to verify that user works. If SSH service breaks, the second terminal stays open and lets you fix it via Hetzner web console.

In your **first terminal** (still on VM as root):

```bash
systemctl reload ssh
echo "ssh reloaded; verify second terminal still works before disconnecting"
```

In **second terminal (local)**:

```bash
ssh -i ~/.ssh/hotmap-hetzner runner@$HETZNER_IP "whoami && hostname"
```

Expected: `runner` and `hotmap-runner-01`. If it works → first terminal can safely exit, and your local SSH config alias `ssh hotmap` works.

If it doesn't: in the first terminal (still root), undo the SSH config:

```bash
rm /etc/ssh/sshd_config.d/99-hotmap.conf
systemctl reload ssh
```

Then debug what went wrong.

- [ ] **Step 3.11 (VM as root, last step): Exit root session**

```bash
exit
```

From now on, all VM operations are as `runner` user (`ssh hotmap`).

---

### Task 4: Install GitHub Actions runner

**Files:** Modifies VM-side; no repo changes yet.

- [ ] **Step 4.1 (browser): Get a registration token**

Open `https://github.com/ansvier/ph-heatmap/settings/actions/runners/new?arch=x64&os=linux` in a browser.

GitHub generates a token visible in the page. Copy it (it expires in 1 hour — use it promptly).

You'll see commands like `./config.sh --url https://github.com/ansvier/ph-heatmap --token AXXXX...`. Copy the token only — we'll write the command ourselves with the `--unattended` flag for non-interactive setup.

- [ ] **Step 4.2 (local): SSH into the VM as `runner`**

```bash
ssh hotmap
```

(Uses the alias from Task 1. If it doesn't work, fall back to `ssh -i ~/.ssh/hotmap-hetzner runner@$HETZNER_IP`.)

- [ ] **Step 4.3 (VM): Download the GitHub Actions runner binaries**

GitHub's official latest URL changes with releases; use the redirect-discovery pattern.

```bash
cd ~
mkdir actions-runner && cd actions-runner

# Find the latest runner version
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
echo "Installing runner version $RUNNER_VERSION"

# Download
curl -o actions-runner-linux-x64-$RUNNER_VERSION.tar.gz \
  -L https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/actions-runner-linux-x64-$RUNNER_VERSION.tar.gz

# Verify the download is reasonable (>50MB)
ls -lh actions-runner-linux-x64-$RUNNER_VERSION.tar.gz

# Extract
tar xzf actions-runner-linux-x64-$RUNNER_VERSION.tar.gz
ls
```

Expected: A bunch of files including `config.sh`, `run.sh`, `svc.sh`, `bin/`, `externals/`.

- [ ] **Step 4.4 (VM): Configure the runner non-interactively**

Replace `PASTE_TOKEN_HERE` with the token from Step 4.1:

```bash
./config.sh \
  --url https://github.com/ansvier/ph-heatmap \
  --token PASTE_TOKEN_HERE \
  --name hotmap-runner-01 \
  --labels self-hosted,linux,x64,hotmap \
  --work _work \
  --unattended \
  --replace
```

`--replace` makes it idempotent if you re-run (e.g., to rotate tokens).

Expected output ending with:
```
√ Connected to GitHub
...
√ Runner successfully added
√ Runner connection is good
...
√ Settings Saved.
```

- [ ] **Step 4.5 (VM): Install the systemd service**

```bash
sudo ./svc.sh install runner
sudo ./svc.sh start
sudo systemctl status actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service --no-pager
```

Expected: `Active: active (running)` in the systemctl output.

- [ ] **Step 4.6 (VM): Verify runner-side processes**

```bash
ps aux | grep -E "Runner.Listener|Runner.Worker" | grep -v grep
journalctl -u "actions.runner.*" --no-pager -n 20
```

Expected: `Runner.Listener` process running, recent journal lines saying "Listening for Jobs".

- [ ] **Step 4.7 (browser): Verify runner appears in GitHub UI**

Open `https://github.com/ansvier/ph-heatmap/settings/actions/runners`.

Expected: A new row `hotmap-runner-01` with green dot "Idle". Labels: `self-hosted`, `linux`, `x64`, `hotmap`.

- [ ] **Step 4.8 (local): Commit the registration record (optional but useful)**

```bash
cd /Users/ansvier/ph-heatmap
cat >> docs/runner-bootstrap.md <<EOF

## Runner registered

- Name: \`hotmap-runner-01\`
- Labels: \`self-hosted, linux, x64, hotmap\`
- Service: \`actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service\`
- Working directory: \`/home/runner/actions-runner/_work\`

To stop/start: \`sudo systemctl stop actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service\` / \`start\`.
To uninstall: \`cd /home/runner/actions-runner && sudo ./svc.sh uninstall && ./config.sh remove --token <removal_token>\`.
EOF

git add docs/runner-bootstrap.md
git commit -m "docs: record runner registration in bootstrap runbook"
```

---

### Task 5: Smoke test — verify PH-from-Hetzner works

**Files:** None (test-only task).

- [ ] **Step 5.1 (local): Trigger a manual workflow run targeted at Linux label**

We haven't flipped the workflow YAML yet — the schedule still hits the Mac mini runner. We need to force the new run to land on the Linux runner. The cleanest way: a one-off override via `workflow_dispatch` with an inputs param, OR just temporarily edit the YAML and revert if smoke fails.

The simpler approach: temporarily flip `runs-on`, push, trigger, observe, and decide whether to keep or revert.

```bash
cd /Users/ansvier/ph-heatmap
# Show current value
grep "runs-on:" .github/workflows/daily-scrape.yml
```

Expected current: `    runs-on: [self-hosted, macOS, arm64]`.

- [ ] **Step 5.2 (local): Edit `.github/workflows/daily-scrape.yml`**

Change the `runs-on` line and the comment above it:

```yaml
    # Self-hosted Linux runner on Hetzner CX22. The GitHub-hosted Ubuntu
    # pool gets Cloudflare-challenged by Pornhub; our own datacenter IP
    # with curl-cffi TLS-fingerprint fallback passes the challenge.
    runs-on: [self-hosted, linux, x64, hotmap]
```

- [ ] **Step 5.3 (local): Commit and push**

```bash
git add .github/workflows/daily-scrape.yml
git commit -m "ops(scrape): point runs-on at the new Hetzner Linux runner"
git push
```

- [ ] **Step 5.4 (local): Trigger the workflow**

```bash
gh workflow run daily-scrape.yml --ref main
sleep 10
gh run list --workflow daily-scrape.yml --limit 2
```

Expected: the latest row has status `queued` or `in_progress`.

- [ ] **Step 5.5 (VM, optional live tail): Watch the runner pick up the job**

```bash
ssh hotmap
journalctl -u "actions.runner.*" -f
```

You'll see "Running job: scrape" within ~10 seconds of the trigger. Ctrl-C to detach (doesn't stop the job).

- [ ] **Step 5.6 (local): Wait for completion + check result**

The full run takes ~25–45 minutes (depends on PH response times). Poll:

```bash
RUN_ID=$(gh run list --workflow daily-scrape.yml --limit 1 --json databaseId --jq '.[0].databaseId')
echo "watching run $RUN_ID"
gh run watch "$RUN_ID"
```

`gh run watch` streams progress and exits when the run finishes.

- [ ] **Step 5.7 (local): Evaluate scrape coverage**

When the run completes, count how many slugs got scraped:

```bash
gh run view "$RUN_ID" --log 2>&1 | grep -E "got [0-9]+ (female|male) slugs|wrote [0-9]+ performer pages|WARN: skipping" | head -20
```

Look for `got 500 female slugs` and `got 500 male slugs` (or close). Compute success rate from `wrote N performer pages` vs the ~870 expected.

**Decision gate:**

- **≥800 performer pages written** → Plan A succeeds. Smoke test green. Proceed to Task 6.
- **<800 written** → PH is blocking the Hetzner IP. Proceed to **Plan B** (Task 5.8 sub-flow below).

- [ ] **Step 5.8 (if needed — Plan B): Add residential proxy**

If smoke fails, sign up at Smartproxy (`https://smartproxy.com/residential-proxies`, ~$12.50/mo for 1 GB) or DataImpulse (~$1/GB pay-as-you-go). Both give you:
- `endpoint:port` (e.g., `gate.smartproxy.com:7000`)
- `username` + `password`

Add the proxy as an env var to the systemd service:

```bash
ssh hotmap
sudo systemctl edit actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service
```

In the editor that opens, paste:

```ini
[Service]
Environment="HTTPS_PROXY=http://USER:PASS@gate.smartproxy.com:7000"
Environment="HTTP_PROXY=http://USER:PASS@gate.smartproxy.com:7000"
```

Save and exit. Then:

```bash
sudo systemctl daemon-reload
sudo systemctl restart actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service
```

Re-trigger smoke (Step 5.4) and re-evaluate (Step 5.7). If still <800, the issue is deeper than IP — escalate (out of scope).

---

### Task 6: Workflow YAML cutover (already done in Task 5)

If smoke test succeeded in Task 5, the cutover is already merged. Task 6 verifies the next scheduled cron lands on the Hetzner runner.

- [ ] **Step 6.1 (local): Verify the change is on origin**

```bash
git log -1 --format="%h %s" -- .github/workflows/daily-scrape.yml
```

Expected: shows the `ops(scrape): point runs-on at the new Hetzner Linux runner` commit.

- [ ] **Step 6.2 (local): Wait for the next scheduled cron (or trigger now)**

The next scheduled run is at 04:17 UTC. To not wait:

```bash
gh workflow run daily-scrape.yml --ref main
gh run list --workflow daily-scrape.yml --limit 1
```

Watch where it runs — the runner-name column in `gh run view <id>` should be `hotmap-runner-01`, not `Mac mini` / the macOS runner name.

```bash
RUN_ID=$(gh run list --workflow daily-scrape.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RUN_ID" --json jobs --jq '.jobs[] | {name, runner_name}'
```

Expected: `{"name": "scrape", "runner_name": "hotmap-runner-01"}`.

---

### Task 7: Retire Mac mini runner

**Files:** Modifies Mac mini runner installation. Updates `README.md`.

- [ ] **Step 7.1 (Mac mini): Stop the GitHub Actions runner service**

On your Mac mini, open Terminal:

```bash
cd ~/actions-runner  # or wherever you installed it
./svc.sh status
./svc.sh stop
./svc.sh uninstall
```

Expected: service stops and uninstalls. The launchd plist gets removed.

- [ ] **Step 7.2 (Mac mini): Get a removal token from GitHub**

In a browser, open `https://github.com/ansvier/ph-heatmap/settings/actions/runners`. Find the row for your Mac mini runner (probably `<your-mac-name>`). Click ⋮ → Remove. GitHub shows a one-shot command including a removal token. Copy the token.

- [ ] **Step 7.3 (Mac mini): Run the removal command**

In the Mac mini's Terminal, in the runner directory:

```bash
./config.sh remove --token PASTE_REMOVAL_TOKEN_HERE
```

Expected: `Runner removed successfully`.

- [ ] **Step 7.4 (browser): Confirm the Mac mini runner is gone**

Refresh `https://github.com/ansvier/ph-heatmap/settings/actions/runners`. Only `hotmap-runner-01` should remain. The Mac mini row is gone.

- [ ] **Step 7.5 (Mac mini, optional): Delete the local runner directory**

```bash
cd ~
rm -rf actions-runner
```

The Mac mini is now fully retired from the project. You can sleep / close / repurpose it.

- [ ] **Step 7.6 (local): Update README to mention Hetzner hosting**

In `/Users/ansvier/ph-heatmap/README.md`, find the "How it works" section and add the Hosting paragraph. Run:

```bash
cd /Users/ansvier/ph-heatmap
```

Open `README.md` and locate the line near the end of the "How it works" section that mentions "Everything runs on free tiers — GitHub Actions (public repo = unlimited minutes), Cloudflare Pages + Worker (static + edge logic), Cloudflare's automatic SSL."

Replace that paragraph with:

```markdown
Everything runs on a single $4/mo Hetzner Cloud CX22 (Ubuntu 24.04 LTS) for the scrape + on Cloudflare's free tier for the public site (Pages + Worker + SSL). GitHub Actions on a public repo gives us unlimited self-hosted runner time. The only ongoing costs are the Hetzner VM (~$50/year) and the domain (~$15/year).
```

- [ ] **Step 7.7 (local): Commit the README change**

```bash
git add README.md
git commit -m "docs(readme): hosting now Hetzner CX22 (\$4/mo) — Mac mini retired"
git push
```

---

### Task 8: Finalize the bootstrap runbook

**Files:** `docs/runner-bootstrap.md` — fills in the bootstrap-steps section and Plan B with the actual verified commands from Tasks 3 + 4.

- [ ] **Step 8.1 (local): Open the runbook**

```bash
cd /Users/ansvier/ph-heatmap
${EDITOR:-vim} docs/runner-bootstrap.md
```

- [ ] **Step 8.2 (local): Replace the placeholder sections**

Find the `## Bootstrap steps` line and the `(filled in by Task 8 ...)` placeholder below it. Replace with this consolidated set of commands (these are verified copies of Tasks 3–4):

```markdown
## Bootstrap steps

Run these on a fresh Hetzner CX22 (Ubuntu 24.04 LTS) after `ssh root@<IP>`:

```bash
# 1. OS patch + packages
apt-get update && apt-get upgrade -y
apt-get install -y \
  python3 python3-venv python3-pip \
  git curl jq \
  ufw fail2ban unattended-upgrades \
  build-essential libssl-dev libcurl4-openssl-dev

# 2. Create runner user
adduser --disabled-password --gecos "" runner
mkdir -p /home/runner/.ssh
cp /root/.ssh/authorized_keys /home/runner/.ssh/authorized_keys
chown -R runner:runner /home/runner/.ssh
chmod 700 /home/runner/.ssh
chmod 600 /home/runner/.ssh/authorized_keys

# 3. Limited sudo for runner-install commands only
echo "runner ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /home/runner/actions-runner/svc.sh" \
  > /etc/sudoers.d/runner
chmod 440 /etc/sudoers.d/runner

# 4. Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

# 5. fail2ban + auto-updates
systemctl enable --now fail2ban
dpkg-reconfigure -plow unattended-upgrades

# 6. SSH hardening
cat > /etc/ssh/sshd_config.d/99-hotmap.conf <<'EOF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
EOF
sshd -t && systemctl reload ssh
```

Then SSH in as `runner@<IP>` and install the GitHub Actions runner:

```bash
# Get registration token from
# https://github.com/ansvier/ph-heatmap/settings/actions/runners/new?os=linux&arch=x64

cd ~
mkdir actions-runner && cd actions-runner
RUNNER_VERSION=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
curl -o actions-runner-linux-x64-$RUNNER_VERSION.tar.gz \
  -L https://github.com/actions/runner/releases/download/v$RUNNER_VERSION/actions-runner-linux-x64-$RUNNER_VERSION.tar.gz
tar xzf actions-runner-linux-x64-$RUNNER_VERSION.tar.gz

./config.sh \
  --url https://github.com/ansvier/ph-heatmap \
  --token PASTE_TOKEN_HERE \
  --name hotmap-runner-01 \
  --labels self-hosted,linux,x64,hotmap \
  --work _work \
  --unattended --replace

sudo ./svc.sh install runner
sudo ./svc.sh start
```

Verify with `sudo systemctl status actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service`. Expected: `Active: active (running)`.
```

- [ ] **Step 8.3 (local): Fill in the Plan B section**

Find the `## Plan B: residential proxy` heading. Replace its placeholder with:

```markdown
## Plan B: residential proxy

If PH starts returning Cloudflare challenges to the Hetzner ASN and per-profile scrape success drops below 80%:

1. Sign up at a residential proxy provider:
   - [Smartproxy Residential](https://smartproxy.com/residential-proxies) — ~$12.50/mo for 1 GB
   - [DataImpulse](https://dataimpulse.com/) — pay-as-you-go, ~$1/GB
2. Get the endpoint and credentials from the dashboard (format: `gate.example.com:7000`, `username:password`).
3. SSH into the runner:
   ```bash
   ssh hotmap
   sudo systemctl edit actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service
   ```
4. Paste:
   ```ini
   [Service]
   Environment="HTTPS_PROXY=http://USER:PASS@gate.example.com:7000"
   Environment="HTTP_PROXY=http://USER:PASS@gate.example.com:7000"
   ```
5. Save and reload:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service
   ```
6. `curl-cffi` honors `HTTPS_PROXY` transparently — no code changes needed.

To disable later: `sudo systemctl edit actions.runner...service` and remove the Environment lines, or replace with empty values.
```

- [ ] **Step 8.4 (local): Commit the finalized runbook**

```bash
git add docs/runner-bootstrap.md
git commit -m "docs(bootstrap): finalize runbook with verified commands + Plan B proxy config"
git push
```

---

## Self-review checklist (filled out by plan author)

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Hetzner Cloud CX22, €3.79/mo | Task 2 |
| Falkenstein DC | Task 2 (step 2.4) |
| Ubuntu 24.04 LTS | Task 2 (step 2.4) |
| Self-hosted runner as systemd service | Task 4 (steps 4.4–4.6) |
| Cached venv at `/home/runner/.cache/ph-heatmap-venv` | Inherited from existing workflow YAML (no change needed; workflow already does this) |
| `unattended-upgrades` configured | Task 3 (step 3.8) |
| `ufw`: deny in / allow 22 | Task 3 (step 3.6) |
| `fail2ban` enabled | Task 3 (step 3.7) |
| SSH password auth disabled, root login disabled | Task 3 (step 3.9) |
| Workflow YAML single-line `runs-on:` change | Task 5 (step 5.2) — done as part of smoke test setup, not a separate task |
| Smoke test ≥80% success threshold | Task 5 (step 5.7) |
| Plan B residential proxy via env var | Task 5 (step 5.8) + Task 8 (step 8.3) |
| Mac mini fully retired | Task 7 (steps 7.1–7.5) |
| README hosting paragraph | Task 7 (step 7.6) |
| Runbook in `docs/runner-bootstrap.md` | Task 1 (scaffold) + Task 8 (finalize) |
| SSH key backup advice | Task 1 (step 1.2) |

No gaps.

**Placeholder scan:** Searched for TBD/TODO/"implement later"/"appropriate"/etc. The only intentional placeholders are:
- `PASTE_TOKEN_HERE` (Step 4.4) — runtime input from GitHub Settings page, must remain placeholder
- `PASTE_REMOVAL_TOKEN_HERE` (Step 7.3) — same, runtime input
- `REPLACE_ME` (Step 2.5) — runtime input, IP from Hetzner
- `<PASTE_IP_AFTER_TASK_2>` (Step 1.3) — explicit, replaced in Step 2.5
- `(filled in by Task 8 ...)` in scaffold (Step 1.4) — finalized in Task 8

All other content is verified commands or descriptive text.

**Type consistency:**
- Runner name `hotmap-runner-01` used identically in Tasks 4, 6, 8.
- Labels `self-hosted, linux, x64, hotmap` used identically in Tasks 4, 5.
- systemd service name `actions.runner.ansvier-ph-heatmap.hotmap-runner-01.service` used identically in Tasks 4, 5, 8.
- SSH alias `hotmap` defined Step 1.3, used in Tasks 3, 4, 5, 7, 8.
- `$HETZNER_IP` env var introduced Step 2.5, used in Steps 2.6, 2.7.

No drift.

**Risk-aware steps:**
- Step 3.10 (SSH restart) explicitly requires a second open session as a safety net.
- Step 5.7 has an explicit "Decision gate" with quantitative threshold (≥800 scraped) before proceeding.
- Step 5.8 is documented as a no-code-change fallback the user can apply without our involvement.
