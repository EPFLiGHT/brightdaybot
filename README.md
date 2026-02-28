# BrightDayBot

A Slack bot that celebrates birthdays with AI-generated personalized messages and images.

## Features

- **AI Messages**: Personalized birthday wishes using OpenAI's latest models
- **AI Images**: Face-accurate images using Slack profile photos
- **Multiple Personalities**: Ludo the Mystic Dog, Captain BirthdayBeard, TechBot 3000, and more
- **Multi-Timezone**: Celebrates at 9 AM in each user's timezone
- **Special Days**: UN/WHO/UNESCO observances and national holidays with AI-generated content
- **Slash Commands**: `/birthday` and `/special-day` with modal forms
- **App Home**: Dashboard with birthday status, statistics, and upcoming events
- **Calendar Export**: Export team birthdays to ICS format
- **Celebration Styles**: Quiet, standard, or epic intensity per user
- **Thread Engagement**: Reacts to birthday thread replies with contextual emojis
- **@-Mention Q&A**: Ask the bot about special days, birthdays, and capabilities
- **NLP Date Parsing**: Set birthday with natural language ("July 14th")
- **Ops Canvas Dashboard**: Auto-updating channel canvas with system health, birthday stats, scheduler, caches, and backups

## Quick Start

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Enable **Socket Mode** with `connections:write` scope
3. Add **Bot Events**: `app_mention`, `member_joined_channel`, `message.channels`, `message.im`, `app_home_opened`
4. Add **Bot Scopes**:
   - Core: `chat:write`, `chat:write.public`, `chat:write.customize`
   - Users: `users:read`, `users.profile:read`
   - Channels: `channels:read`, `channels:history`, `channels:manage`, `groups:read`, `groups:history`, `groups:write`, `mpim:read`
   - DMs: `im:write`, `im:read`, `im:history`
   - Files: `files:read`, `files:write`
   - Reactions: `reactions:read`, `reactions:write`
   - Canvas: `canvases:write`, `pins:write`
   - Other: `emoji:read`, `app_mentions:read`, `commands`
5. Add **Slash Commands**: `/birthday`, `/special-day`
6. Enable **Interactivity & Shortcuts** (for modal forms)
7. Enable **App Home** → Home Tab
8. Install to workspace

### 2. Install Dependencies

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Setup crawl4ai browser (for web-scraped observances)
uv run crawl4ai-setup
```

### 3. Configure and Run

```bash
cp .env.example .env
# Edit .env with your actual tokens (see .env.example for all options)
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

For production deployment, see [Production Deployment](#production-deployment).

## Commands

### Slash Commands

| Command                        | Description                      |
| ------------------------------ | -------------------------------- |
| `/birthday`                    | Open birthday form               |
| `/birthday check [@user]`      | Check birthday                   |
| `/birthday list`               | List upcoming birthdays          |
| `/birthday export`             | Export birthdays to ICS calendar |
| `/birthday pause`              | Pause birthday celebrations      |
| `/birthday resume`             | Resume birthday celebrations     |
| `/birthday help`               | Show birthday command help       |
| `/special-day`                 | Today's special days             |
| `/special-day week`            | Next 7 days                      |
| `/special-day month`           | Next 30 days                     |
| `/special-day export [source]` | Export special days to ICS       |

### User Commands (DM the bot)

> [!TIP]
> Slash commands and App Home are the recommended ways to interact. DM commands are available as an alternative.

| Command                               | Description                  |
| ------------------------------------- | ---------------------------- |
| `add DD/MM [YYYY]`                    | Set your birthday            |
| `check [@user]`                       | View birthday                |
| `remove`                              | Remove your birthday         |
| `pause`                               | Pause birthday celebrations  |
| `resume`                              | Resume birthday celebrations |
| `test [quality] [size] [--text-only]` | Preview birthday message     |
| `special`                             | Today's special days         |
| `help`                                | Show commands                |

### Admin Commands

| Command                                        | Description                     |
| ---------------------------------------------- | ------------------------------- |
| `admin status [detailed]`                      | System health check             |
| `admin model set <model>`                      | Change AI model                 |
| `admin personality [name]`                     | View or change bot personality  |
| `admin timezone enable/disable`                | Toggle timezone mode            |
| `admin test @user [--text-only]`               | Test for specific user          |
| `admin announce [message]`                     | Send announcement               |
| `admin canvas [status\|refresh\|reset\|clean]` | Manage ops canvas dashboard     |
| `admin special [subcommand]`                   | Special days management         |
| `admin backup`                                 | Manual birthday data backup     |
| `admin restore latest`                         | Restore from latest backup      |
| `admin cache clear [DD/MM]`                    | Clear web search cache          |
| `admin config`                                 | View/change command permissions |
| `admin remind [new\|update\|all]`              | Send reminders to users         |
| `admin list/add/remove`                        | Admin user management           |
| `admin stats`                                  | Birthday statistics             |
| `list`                                         | View all birthdays              |

## Personalities

| Name            | Style                     |
| --------------- | ------------------------- |
| `standard`      | Friendly default          |
| `mystic_dog`    | Cosmic predictions (Ludo) |
| `poet`          | Lyrical verses            |
| `tech_guru`     | Programming themes        |
| `chef`          | Culinary celebrations     |
| `superhero`     | Comic book heroics        |
| `time_traveler` | Sci-fi adventures         |
| `pirate`        | Nautical swashbuckling    |
| `gardener`      | Nature, growth themes     |
| `philosopher`   | Wisdom, life's journey    |
| `chronicler`    | Historical (special days) |
| `random`        | Surprise selection        |
| `custom`        | User-configurable         |

## Configuration

All optional settings are documented in [`.env.example`](.env.example) with defaults and descriptions. Key categories:

- **AI & Core**: Model selection, image generation, backups
- **Special Days Sources**: UN/UNESCO/WHO cache TTLs, Calendarific API
- **Interactive Features**: Thread engagement, @-mention Q&A, NLP date parsing
- **Announcements**: @-here mentions, channel topic updates
- **Canvas Dashboard**: Ops channel with auto-updating system overview
- **Custom Personality**: Name, description, style, formatting

## Project Structure

```text
brightdaybot/
├── app.py                        # Entry point
├── Dockerfile                    # Docker image definition
├── docker-compose.yml            # Docker Compose configuration
├── pyproject.toml                # Project metadata & dependencies
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
│   ├── calendarific.py           # National holiday API
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
    └── cache/                    # Images, profiles, observances
```

## Production Deployment

### Option A: Docker + systemd (Recommended)

Docker handles dependencies, Playwright browsers, and isolation. systemd ensures the bot starts on boot and restarts on failure. Data is stored on the host via volume mounts, not inside the container.

```bash
cd /path/to/brightdaybot
cp .env.example .env
# Edit .env with your actual tokens

# Test the setup
docker compose up --build
```

```ini
# /etc/systemd/system/brightdaybot.service
[Unit]
Description=BrightDayBot (Docker)
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/path/to/brightdaybot
ExecStart=/usr/bin/docker compose up --build
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=30
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot

# Useful commands
sudo systemctl status brightdaybot     # Check status
sudo journalctl -u brightdaybot -f     # Follow logs
sudo systemctl restart brightdaybot    # Restart after code changes
```

### Option B: systemd with uv (No Docker)

Run the bot directly with uv. Requires manual Playwright browser setup.

```bash
# Install uv system-wide
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo mv ~/.local/bin/uv /usr/local/bin/

# Install dependencies and configure environment
cd /path/to/brightdaybot
uv sync
cp .env.example .env
# Edit .env with your actual tokens

# Setup Playwright browsers
sudo mkdir -p /opt/playwright && sudo chmod -R 777 /opt/playwright
PLAYWRIGHT_BROWSERS_PATH=/opt/playwright uv run crawl4ai-setup

# If crawl4ai-setup fails with permission errors on /opt/playwright/.links/,
# install browsers manually:
PLAYWRIGHT_BROWSERS_PATH=/opt/playwright uv run python -m patchright install chromium --with-deps
```

```ini
# /etc/systemd/system/brightdaybot.service
[Unit]
Description=BrightDayBot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/uv run python app.py
WorkingDirectory=/path/to/brightdaybot
Restart=always
RestartSec=30
Environment="PLAYWRIGHT_BROWSERS_PATH=/opt/playwright"

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now brightdaybot
```

## Troubleshooting

1. **Health check**: `admin status` in Slack
2. **Logs**: Check `data/logs/` (`main.log`, `commands.log`, `ai.log`, `birthday.log`, `slack.log`, `storage.log`, `system.log`, `scheduler.log`, `events.log`)
3. **Common issues**:
   - Missing API keys → Check `.env`
   - Image failures → Verify OpenAI key has image access
   - Timezone issues → User must set timezone in Slack profile
   - Playwright browser not found (Docker) → Rebuild with `docker compose up -d --build`
   - Playwright browser not found (uv) → Run `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright uv run python -m patchright install chromium --with-deps` and restart the service

## License

See [LICENSE](LICENSE).
