# BrightDayBot Auto-Deploy Setup

A systemd timer checks for code changes every 5 minutes. When updates are found, it pulls and restarts the `brightdaybot` service (which rebuilds via `docker compose up --build`).

## Prerequisites

Clone the repo on the server (public repo, no token needed):

```bash
git clone https://github.com/EPFLiGHT/brightdaybot.git /path/to/brightdaybot
git fetch origin main  # verify access
```

> For private repos, use an HTTPS token (`https://<TOKEN>@github.com/...`) or an SSH deploy key.

## Installation

1. Edit `brightdaybot-updater.service` — set `BRIGHTDAYBOT_DIR` and `WorkingDirectory` to your repo path.

2. Install:

```bash
chmod +x deploy/auto-update.sh

sudo cp deploy/brightdaybot-updater.service /etc/systemd/system/
sudo cp deploy/brightdaybot-updater.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot-updater.timer
```

## Usage

```bash
systemctl status brightdaybot-updater.timer        # check timer
journalctl -u brightdaybot-updater -f              # view logs
sudo systemctl start brightdaybot-updater.service   # trigger now
sudo systemctl disable --now brightdaybot-updater.timer  # disable
```
