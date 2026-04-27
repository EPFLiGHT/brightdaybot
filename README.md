<p align="center">
  <img src="assets/logo.png" alt="BrightDayBot" width="200">
</p>

<h1 align="center">BrightDayBot</h1>

<p align="center">
  AI-driven Slack bot that orchestrates team birthday celebrations and curates international observances — with distinct personalities, face-accurate imagery, and web-scraped observance calendars.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue">
  <img src="https://img.shields.io/github/license/EPFLiGHT/brightdaybot">
  <img src="https://img.shields.io/github/actions/workflow/status/EPFLiGHT/brightdaybot/ci.yml?branch=main&label=CI">
</p>

<p align="center">
  <a href="#quick-start"><strong>Get Started</strong></a> &middot;
  <a href="#commands"><strong>Commands</strong></a> &middot;
  <a href="#personalities"><strong>Personalities</strong></a> &middot;
  <a href="#configuration"><strong>Configuration</strong></a>
</p>

---

## Features

- **AI Messages**: Personalized birthday wishes using OpenAI's latest models
- **AI Images**: Face-accurate images using Slack profile photos
- **Multiple Personalities**: Ludo the Mystic Dog, Captain BirthdayBeard, TechBot 3000, and more
- **Multi-Timezone**: Celebrates at 9 AM in each user's timezone
- **Special Days**: International observances (UN, UNESCO, WHO), national holidays (Calendarific), ICS calendar feed subscriptions, and CSV custom days with AI-generated content, consolidated into a single daily announcement
- **Slash Commands**: `/birthday` and `/special-day` with modal forms
- **App Home**: Dashboard with birthday status, statistics, and upcoming events
- **Calendar Export**: Export team birthdays to ICS format
- **Celebration Styles**: Quiet, standard, or epic intensity per user
- **Thread Engagement**: Reacts to birthday thread replies with contextual emojis
- **@-Mention Q&A**: Ask the bot about special days, birthdays, and capabilities
- **NLP Date Parsing**: Set birthday with natural language ("July 14th")
- **Ops Canvas Dashboard**: Auto-updating channel canvas with system health, birthday stats, deploy info, scheduler, caches, and backups
- **Deploy Notifications**: Slack ops channel alerts on deploy success, failure, and rollback

## Quick Start

### 1. Create Slack App

Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App**

- Enable **Socket Mode** with `connections:write` scope
- Add **Slash Commands**: `/birthday`, `/special-day`
- Enable **Interactivity & Shortcuts** and **App Home** → Home Tab

<details>
<summary><strong>Required bot scopes</strong></summary>

- **Core**: `chat:write`, `chat:write.public`, `chat:write.customize`
- **Users**: `users:read`, `users.profile:read`
- **Channels**: `channels:read`, `channels:history`, `channels:manage`, `groups:read`, `groups:history`, `groups:write`, `mpim:read`
- **DMs**: `im:write`, `im:read`, `im:history`
- **Files**: `files:read`, `files:write`
- **Reactions**: `reactions:read`, `reactions:write`
- **Canvas**: `canvases:write`, `pins:write`
- **Other**: `emoji:read`, `app_mentions:read`, `commands`

**Bot Events**: `app_mention`, `member_joined_channel`, `message.channels`, `message.im`, `app_home_opened`

</details>

### 2. Install Dependencies

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # Install uv (if needed)
uv sync                                           # Install dependencies
uv run crawl4ai-setup                             # Setup browser for observance scraping
```

### 3. Configure and Run

```bash
cp .env.example .env
# Edit .env with your tokens
```

**Required in `.env`:**

```env
SLACK_BOT_TOKEN="xoxb-..."
SLACK_APP_TOKEN="xapp-..."
BIRTHDAY_CHANNEL_ID="C..."
OPENAI_API_KEY="sk-..."
```

```bash
uv run python app.py
```

> [!TIP]
> For production, see [Production Deployment](#production-deployment).

## Commands

<details open>
<summary><strong>Slash Commands</strong></summary>

| Command                        | Description                      |
| ------------------------------ | -------------------------------- |
| `/birthday`                    | Open birthday form               |
| `/birthday check [@user]`      | Check birthday                   |
| `/birthday list`               | List upcoming birthdays          |
| `/birthday export`             | Export birthdays to ICS calendar |
| `/birthday pause` / `resume`   | Pause or resume celebrations     |
| `/birthday help`               | Show birthday command help       |
| `/special-day`                 | Today's special days             |
| `/special-day week` / `month`  | Next 7 or 30 days                |
| `/special-day export [source]` | Export special days to ICS       |

</details>

<details>
<summary><strong>User Commands (DM)</strong></summary>

**💡 Tip:** Slash commands and App Home are the recommended ways to interact. DM commands are available as an alternative.

| Command                               | Description                  |
| ------------------------------------- | ---------------------------- |
| `add DD/MM [YYYY]`                    | Set your birthday            |
| `check [@user]`                       | View birthday                |
| `remove`                              | Remove your birthday         |
| `pause` / `resume`                    | Pause or resume celebrations |
| `test [quality] [size] [--text-only]` | Preview birthday message     |
| `special`                             | Today's special days         |
| `help`                                | Show commands                |

</details>

<details>
<summary><strong>Admin Commands</strong></summary>

| Command                                                          | Description                     |
| ---------------------------------------------------------------- | ------------------------------- |
| `admin status [detailed]`                                        | System health check             |
| `admin model set <model>`                                        | Change AI text model            |
| `admin image-model set <model>`                                  | Change AI image model           |
| `admin personality [name]`                                       | View or change bot personality  |
| `admin timezone enable/disable`                                  | Toggle timezone mode            |
| `admin bot-celebration enable/disable`                           | Toggle bot self-celebration     |
| `admin test @user [--text-only]`                                 | Test for specific user          |
| `admin announce [message]`                                       | Send announcement               |
| `admin canvas [status\|refresh\|reset\|clean\|dismiss-warnings]` | Manage ops canvas dashboard     |
| `admin special [subcommand]`                                     | Special days management         |
| `admin special ics-add <url> "Label"`                            | Subscribe to ICS calendar feed  |
| `admin special ics-list/remove/toggle/refresh/test`              | Manage ICS subscriptions        |
| `admin backup` / `admin restore latest`                          | Backup operations               |
| `admin cache clear [DD/MM]`                                      | Clear web search cache          |
| `admin config`                                                   | View/change command permissions |
| `admin remind [new\|update\|all]`                                | Send reminders to users         |
| `admin list/add/remove`                                          | Admin user management           |
| `admin stats`                                                    | Birthday statistics             |

</details>

## Personalities

Each personality brings a unique voice, writing style, and image aesthetic to celebrations.

|     | ID              | Name                  | Style                     |
| :-: | --------------- | --------------------- | ------------------------- |
| 🌞  | `standard`      | BrightDay             | Friendly default          |
| 🐕  | `mystic_dog`    | Ludo                  | Cosmic predictions        |
| 📜  | `poet`          | The Verse-atile       | Lyrical verses            |
| 💻  | `tech_guru`     | TechBot 3000          | Programming themes        |
| 👨‍🍳  | `chef`          | Chef Confetti         | Culinary celebrations     |
| 🦸  | `superhero`     | Captain Celebration   | Comic book heroics        |
| ⏰  | `time_traveler` | Chrono                | Sci-fi adventures         |
| 🏴‍☠️  | `pirate`        | Captain BirthdayBeard | Nautical swashbuckling    |
| 🌿  | `gardener`      | Bloom                 | Nature, growth themes     |
| 🦉  | `philosopher`   | The Sage              | Wisdom, life's journey    |
| 📚  | `chronicler`    | The Chronicler        | Historical (special days) |
| 🎲  | `random`        | Surprise Bot          | Random selection          |
| ⚙️  | `custom`        | Custom Bot            | User-configurable         |

## Configuration

All optional settings are documented in [`.env.example`](.env.example) with defaults and descriptions. Key categories:

- **AI & Core**: Model selection, image generation, backups
- **Special Days Sources**: Observance cache TTLs, multi-source Calendarific holidays, ICS feed subscriptions
- **Interactive Features**: Thread engagement, @-mention Q&A, NLP date parsing
- **Announcements**: @-here mentions, channel topic updates, consolidated special days
- **Canvas Dashboard**: Ops channel with auto-updating system overview
- **Custom Personality**: Name, description, style, formatting

## Project Structure

<details>
<summary><strong>View directory layout</strong></summary>

```text
brightdaybot/
├── app.py                        # Entry point
├── Dockerfile                    # Docker image definition
├── docker-compose.yml            # Docker Compose configuration
├── pyproject.toml                # Project metadata & dependencies
├── deploy/                       # Deployment (shadow build + symlink cutover)
├── config/                       # Configuration package
│   ├── __init__.py               # Re-exports (backward compatibility)
│   ├── settings.py               # Core settings, API parameters
│   ├── personality.py            # Personality helpers
│   └── personality_data.py       # Personality data constants
├── commands/                     # Command processors
│   ├── admin_commands.py         # Admin operations
│   ├── birthday_commands.py      # Birthday CRUD
│   ├── special_day_commands.py   # Special days management
│   └── test_commands.py          # Testing commands
├── handlers/                     # Slack event handlers
│   ├── app_home_handler.py       # App Home dashboard
│   ├── event_handler.py          # DM & channel events
│   ├── mention_handler.py        # @-mention Q&A
│   ├── modal_handler.py          # Birthday form modal
│   ├── slash_handler.py          # /birthday, /special-day
│   └── thread_handler.py         # Thread reactions
├── services/                     # Business logic
│   ├── birthday.py               # Celebrations
│   ├── celebration.py            # Pipeline & validation
│   ├── dispatcher.py             # Command routing
│   ├── image_generator.py        # AI image generation
│   ├── mention_responder.py      # @-mention responses
│   ├── message_generator.py      # AI message generation
│   ├── scheduler.py              # Background tasks
│   └── special_day.py            # Special day messages
├── integrations/                 # External API clients
│   ├── calendarific.py           # Multi-source holiday API
│   ├── ics_feed.py               # External ICS calendar subscriptions
│   ├── openai.py                 # OpenAI API
│   ├── web_search.py             # Historical facts
│   └── observances/              # Web-scraped sources
│       ├── base.py               # Base scraper class
│       ├── un.py                 # UN international days
│       ├── unesco.py             # UNESCO international days
│       └── who.py                # WHO health campaigns
├── slack/                        # Slack API layer
│   ├── canvas.py                 # Ops channel canvas dashboard
│   ├── client.py                 # User profiles, permissions, channels
│   ├── emoji.py                  # Emoji selection & management
│   ├── messaging.py              # Message sending & file uploads
│   └── blocks/                   # Block Kit builders
│       ├── __init__.py           # Re-exports all block functions
│       ├── admin.py              # Admin/status blocks
│       ├── birthday.py           # Birthday blocks
│       ├── help.py               # Help & welcome blocks
│       └── special_day.py        # Special day blocks
├── storage/                      # Data persistence
│   ├── birthdays.py              # Birthday storage
│   ├── settings.py               # Dynamic config
│   ├── special_days.py           # Special days (multi-source)
│   └── thread_tracking.py        # Thread tracking
├── utils/                        # Pure utilities
│   ├── date_parsing.py           # Natural language dates
│   ├── date_utils.py             # Date parsing, star signs
│   ├── health.py                 # System health
│   ├── ics.py                    # ICS calendar generation
│   ├── log_setup.py              # Logging setup
│   └── sanitization.py           # Input sanitization
├── tests/                        # Test suite
│   ├── conftest.py               # Shared fixtures
│   └── test_*.py                 # Unit & integration tests
└── data/
    ├── storage/                  # Birthday data, configs
    ├── logs/                     # Component log files
    ├── tracking/                 # Duplicate prevention
    ├── backups/                  # Auto backups
    └── cache/                    # Images, profiles, observances, calendarific, ics_feeds
```

</details>

## Production Deployment

Uses shadow builds with atomic symlink cutover — new versions are built and validated before switching, with automatic rollback on failure. See [`deploy/README.md`](deploy/README.md) for the full guide.

<details open>
<summary><strong>Quick Start</strong></summary>

```bash
# 1. Set up directory structure
sudo deploy/setup.sh /opt/brightdaybot https://github.com/EPFLiGHT/brightdaybot.git

# 2. Configure secrets
cp .env.example /opt/brightdaybot/shared/.env
# Edit with your actual tokens

# 3. First deploy
sudo BRIGHTDAYBOT_BASE=/opt/brightdaybot /opt/brightdaybot/repo/deploy/deploy.sh

# 4. Install systemd units — pick ONE service file:
#    Docker (recommended):
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot.service /etc/systemd/system/
#    Native uv (requires manual Playwright setup):
# sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-uv.service /etc/systemd/system/brightdaybot.service

sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-updater.service /etc/systemd/system/
sudo cp /opt/brightdaybot/repo/deploy/brightdaybot-updater.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot
sudo systemctl enable --now brightdaybot-updater.timer
```

Auto-deploys every 5 minutes: fetches, builds in staging, validates, swaps symlink, restarts, verifies health. Old version keeps running until the new one passes all checks.

</details>

### Managing the Service

```bash
sudo systemctl status brightdaybot                 # Check status
sudo journalctl -u brightdaybot -f                 # Follow logs
sudo journalctl -u brightdaybot-deploy -n 50       # Deploy logs
sudo systemctl start brightdaybot-updater.service  # Trigger deploy now
readlink /opt/brightdaybot/current                 # Current release
sudo /opt/brightdaybot/repo/deploy/rollback.sh     # Instant rollback
```

## Troubleshooting

1. **Health check**: `admin status` in Slack
2. **Logs**: Check `data/logs/` — `main.log`, `commands.log`, `ai.log`, `birthday.log`, `slack.log`, `storage.log`, `system.log`, `scheduler.log`, `events.log`
3. **Common issues**:
   - Missing API keys → Check `.env`
   - Image failures → Verify OpenAI key has image access
   - Timezone issues → User must set timezone in Slack profile
   - Playwright not found (Docker) → `docker compose up -d --build`
   - Playwright not found (uv) → `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright uv run python -m patchright install chromium --with-deps`

## License

See [LICENSE](LICENSE).
