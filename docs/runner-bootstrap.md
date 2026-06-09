# HotMap Runner Bootstrap

The HotMap daily-scrape workflow runs on a single self-hosted GitHub
Actions runner on a Hetzner Cloud CX23 (~$5/mo). This file is the
runbook for setting up a fresh runner from zero — useful if the VM
dies, is migrated, or replaced.

## Server

- Provider: Hetzner Cloud
- Plan: CX23 (2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB transfer)
- Region: Falkenstein (`fsn1`)
- OS: Ubuntu 26.04 LTS
- IP: 167.233.111.75
- SSH alias: `ssh hotmap` (configured locally via `~/.ssh/config`)

## Bootstrap steps

(to be finalized in Task 8 with verified commands)

## Plan B: residential proxy

(to be finalized in Task 8)
