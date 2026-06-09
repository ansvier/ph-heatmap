# Runner Migration to Hetzner — design

**Status:** approved
**Date:** 2026-06-09
**Author:** ansvier + claude

## Problem

The daily-scrape GitHub Actions workflow runs on a self-hosted runner installed on the user's personal Mac mini at home (residential IP in Russia). When the user closes the laptop / loses connectivity / reboots, the runner goes offline and the cron silently misses days. Recent failure cluster: 06-07 missed entirely, 06-08 partial (91 of 870 slugs), 06-09 needed manual intervention. The Mac mini was the right bootstrap choice — residential IP, free, hands-on — but maintenance friction has compounded and the user wants the project to run hands-off.

## Goal

After this lands:

1. The daily-scrape workflow runs from a Hetzner Cloud VM that's powered on 24/7.
2. The user's Mac mini is fully retired from the project — no GitHub Actions runner installed, no expectation that it must be online for any HotMap operation.
3. The new runner survives reboots automatically (systemd service auto-start).
4. The OS auto-patches via `unattended-upgrades`.
5. If PH blocks the datacenter ASN, there's a documented fallback path (residential proxy) that doesn't require re-architecting.
6. The workflow YAML is the minimum-viable change — `runs-on` label flip, nothing else.

## Decision

### 1. Server choice

**Hetzner Cloud CX22**, €3.79/month (~$4.10).

- 1 vCPU shared, 2 GB RAM, 40 GB SSD, 20 TB outbound transfer/mo
- Datacenter: Falkenstein, Germany (`fsn1`)
- OS: Ubuntu 24.04 LTS (supported until April 2029)
- Architecture: x86_64

Why not DigitalOcean basic ($4 droplet) or Vultr ($2.50): both have 512 MB RAM in the entry tier; our scraper occasionally peaks ~400 MB (Plotly + pandas + 873 performer photos in memory during render), and an OOM kill in the middle of the daily run would cause silent data loss. The 2 GB headroom is worth the ~$1/month delta.

### 2. Runner setup

Install GitHub Actions self-hosted runner as a systemd service:

```
/home/runner/actions-runner/   ← runner binaries
/home/runner/.cache/ph-heatmap-venv/   ← cached Python venv
/etc/systemd/system/actions.runner.<org>-<repo>.<runner-name>.service   ← managed by ./svc.sh install
```

The runner registers against `ansvier/ph-heatmap` using a registration token from `Settings → Actions → Runners → New self-hosted runner`. Tags applied: `self-hosted, linux, x64, hotmap`.

### 3. Workflow YAML change

Single line in `.github/workflows/daily-scrape.yml`:

```yaml
# Before
runs-on: [self-hosted, macOS, arm64]
# After
runs-on: [self-hosted, linux, x64]
```

Everything else stays — the cached-venv block, env vars, commit/push steps. `python3` and the bash semantics are compatible between macOS and Ubuntu.

### 4. Operating-system hardening

Minimal but reasonable defaults:

- `unattended-upgrades` package configured for `security` and `updates` channels — applies security patches nightly without intervention
- `ufw` firewall: deny incoming all, allow tcp/22 (SSH) from anywhere
- `fail2ban` for SSH (default jail) — automatic temp-ban on brute-force attempts
- SSH password auth disabled (`PasswordAuthentication no` in `/etc/ssh/sshd_config`) — key-only
- Root SSH disabled (`PermitRootLogin no`)
- One unprivileged user `runner` (owns the GH Actions runner installation)
- Time sync via `systemd-timesyncd` (default on Ubuntu) — cron timing accurate

### 5. Bootstrap automation

Document everything in `docs/runner-bootstrap.md` as a runbook the user can read once and a future-self (or replacement server) can re-execute. Steps captured as bash commands, not a complex provisioning system — we're configuring exactly one VM, infrastructure-as-code would be overkill.

### 6. Backup and recovery

- **Git repo IS the backup** — every state (data.db, public/, code) lives in `main` on GitHub. If the VM is lost, spinning up a new one is just: bootstrap from runbook + clone repo + install runner + workflow runs tomorrow.
- **No application-level backups needed.** SQLite `data.db` and rendered HTML are products of the daily scrape; if the runner dies mid-week, the next successful run reconstructs everything.
- **SSH key backup**: user's responsibility — save `~/.ssh/hotmap-hetzner` to a password manager. Document this in the runbook.

### 7. PH-blocking fallback (Plan B)

If post-migration smoke shows PH blocks the Hetzner ASN (cloud datacenter IP):

**Stage 1 — try without proxy:** We added TLS-fingerprint fallback in `scraper.py` last week (commit `6ff99d79`). On a Hetzner box this might be enough — Cloudflare's challenge logic is fingerprint-aware, not pure-ASN. Verified by smoke test: run scraper end-to-end, count successful parses. ≥80% success = ship it.

**Stage 2 — if <80%, add residential proxy:** Cheapest acceptable provider — Smartproxy Residential ($12/mo for 2 GB) or Bright Data starter (~$15). Set `HTTPS_PROXY=http://user:pass@proxy.host:port` env var in the systemd service; curl-cffi honors it transparently. No code changes required — only env var + restart.

**Stage 3 — if even residential proxy fails:** Out of scope here. Would require deeper anti-bot work (CAPTCHA-solving services, etc.). At that point the project's economics fundamentally change and we'd discuss separately.

### 8. Migration flow

1. **Pre-migration:** Document the runbook in repo. Verify Mac mini's current scrape state (no in-progress runs).
2. **Provision Hetzner:** Create account → add SSH key → spin up CX22 in `fsn1` → note IP.
3. **Bootstrap server:** SSH in, run the runbook commands (~45 min wall clock, ~5 min keystrokes).
4. **Register runner:** Generate token in GH Settings, run `./config.sh` with `--unattended` flag for non-interactive setup.
5. **Smoke test:** Trigger workflow_dispatch from `gh workflow run`. Watch logs. If 800+ slugs scraped → migration successful.
6. **Update YAML:** Single-line `runs-on:` change. Push. Next scheduled cron runs on Hetzner.
7. **Retire Mac mini:** Stop the GH Actions runner service on Mac mini (`./svc.sh uninstall`), unregister from GH Settings, mark `[self-hosted, macOS, arm64]` as decommissioned (or remove the runner from GH UI). Mac mini can now sleep / be repurposed.

### 9. Cost & ongoing maintenance

| Item | Cost | Frequency |
|---|---|---|
| Hetzner CX22 | €3.79/mo (~$4.10) | Monthly auto-charge |
| Plan B: residential proxy (if needed) | $12-15/mo | Monthly, optional |
| Domain (existing) | $15/yr | Annual |
| GitHub Actions on self-hosted | $0 | Always free for public repos |
| Cloudflare Pages + Worker | $0 | Always free tier |

**Total worst case:** ~$20/mo if residential proxy needed. Best case: ~$4/mo.

Maintenance burden after setup:
- OS patches applied automatically (`unattended-upgrades`)
- No application updates needed (runner auto-updates within minor version per GH Actions runner policy)
- Manual touch every ~6 months: ssh in, `sudo apt update && sudo apt upgrade -y`, verify runner status, look at uptime — 5-minute job

## Scope

### In scope

- Provision Hetzner CX22, Ubuntu 24.04 LTS
- Bootstrap script / runbook in `docs/runner-bootstrap.md`
- Install + configure GitHub Actions runner as systemd service
- Configure `unattended-upgrades`, `ufw`, `fail2ban`, SSH hardening
- Update `daily-scrape.yml` for Linux runner
- Smoke test + verify ≥800 slugs scraped
- Retire Mac mini runner (uninstall + GH unregister)
- Document migration in README footer ("Built on Hetzner, ~$4/mo")
- Plan B documentation (residential proxy env-var-only setup) without implementing it yet

### Out of scope

- High-availability multi-runner setup (overkill for single daily cron)
- Geographic redundancy (Hetzner outages are rare; cron watchdog catches single-day misses)
- Switching scraper to a serverless model (Cloudflare Workers + Python via Pyodide — major rewrite)
- Provisioning IaC (Terraform / Ansible / Pulumi — one VM doesn't need it)
- Automated proxy fallback (manual env-var change is acceptable if Plan B triggers)
- Mac mini repurposing — user's call, not our concern

## Risks

- **PH blocks Hetzner ASN entirely** (medium probability). Mitigated by TLS-fingerprint fallback added last week + documented Plan B (residential proxy). Worst case: smoke test reveals it, we add proxy env var, no code change.
- **SSH key loss** (low probability). Mitigated by user-side key backup discipline (1Password). If lost: Hetzner web console reset → re-bootstrap.
- **Server compromise via SSH brute-force** (low). Mitigated by fail2ban + key-only auth + non-default user.
- **Hetzner billing failure / account suspension** (low). Mitigated by valid card on file + email notifications. Recovery: provision new VM, re-bootstrap (1 hour).
- **Single-runner dependency** (medium). Mitigated by cron watchdog (already deployed) that retries within 18 minutes. Real failures still mean missed daily snapshot — we accept this for $4/mo.

## Files touched

| Path | Change |
|---|---|
| `.github/workflows/daily-scrape.yml` | Single-line `runs-on:` flip + remove stale macOS-specific comment |
| `docs/runner-bootstrap.md` | New runbook documenting Hetzner setup, runner install, hardening, Plan B proxy config |
| `README.md` | Add "Hosting" subsection under "How it works" mentioning Hetzner ~$4/mo |

**Total:** ~80 lines of runbook, 2 lines of workflow YAML change, ~6 lines of README. No Python code changes. No new dependencies.
