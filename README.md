# BrightDayBot

A Slack bot that celebrates birthdays with AI-generated personalized messages and images.

## Features

- **AI Messages**: Personalized birthday wishes using OpenAI's latest models
- **AI Images**: Face-accurate images using Slack profile photos
- **Multiple Personalities**: Ludo the Mystic Dog, Captain BirthdayBeard, TechBot 3000, and more
- **Multi-Timezone**: Celebrates at 9 AM in each user's timezone
- **Special Days**: UN/WHO/UNESCO observances with AI-generated content
- **Smart Consolidation**: Single message for multiple same-day birthdays
- **Slash Commands**: `/birthday` and `/special-day` with modal forms
- **App Home**: Dashboard with birthday status and upcoming birthdays
- **Block Kit UI**: Professional Slack message layouts

## Quick Start

### 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Enable **Socket Mode** with `connections:write` scope
3. Add **Bot Events**: `app_mention`, `member_joined_channel`, `message.channels`, `message.im`, `app_home_opened`
4. Add **Bot Scopes**: `chat:write`, `chat:write.public`, `users:read`, `users.profile:read`, `files:write`, `channels:read`, `im:write`, `im:read`, `emoji:read`, `commands`
5. Add **Slash Commands**: `/birthday`, `/special-day`
6. Enable **Interactivity & Shortcuts** (for modal forms)
7. Enable **App Home** → Home Tab
8. Install to workspace

### 2. Configure Environment

```bash
pip install -r requirements.txt
cp .env.example .env
```

**Required in `.env`:**

```env
SLACK_BOT_TOKEN="xoxb-..."
SLACK_APP_TOKEN="xapp-..."
BIRTHDAY_CHANNEL_ID="C..."
OPENAI_API_KEY="sk-..."
```

### 3. Run

```bash
python app.py
```

## Commands

### Slash Commands (Use Anywhere)

| Command                   | Description             |
| ------------------------- | ----------------------- |
| `/birthday`               | Open birthday form      |
| `/birthday add`           | Open birthday form      |
| `/birthday check [@user]` | Check birthday          |
| `/birthday list`          | List upcoming birthdays |
| `/special-day`            | Today's special days    |
| `/special-day week`       | Next 7 days             |
| `/special-day month`      | Next 30 days            |

### User Commands (DM the bot)

| Command              | Description              |
| -------------------- | ------------------------ |
| `add DD/MM [YYYY]`   | Set your birthday        |
| `check`              | View your birthday       |
| `remove`             | Remove your birthday     |
| `test [--text-only]` | Preview birthday message |
| `special`            | Today's special days     |
| `help`               | Show commands            |

### Admin Commands

| Command                          | Description            |
| -------------------------------- | ---------------------- |
| `admin status`                   | System health check    |
| `admin model set <model>`        | Change AI model        |
| `admin personality <name>`       | Change bot personality |
| `admin timezone enable/disable`  | Toggle timezone mode   |
| `admin test @user [--text-only]` | Test for specific user |
| `admin announce`                 | Send announcement      |
| `list`                           | View all birthdays     |

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

### Optional Environment Variables

```env
OPENAI_MODEL="gpt-4.1"              # AI model (default: gpt-4.1)
AI_IMAGE_GENERATION_ENABLED="true"  # Enable AI images
EXTERNAL_BACKUP_ENABLED="true"      # Backup to admin DMs
CALENDARIFIC_API_KEY="..."          # For national/local holidays
CALENDARIFIC_ENABLED="true"         # Enable Calendarific integration
```

### Special Days Setup (Optional)

```bash
# UN Observances (requires crawl4ai)
pip install crawl4ai && crawl4ai-setup

# Calendarific holidays (optional, 500 free calls/month)
# Add to .env: CALENDARIFIC_API_KEY="..." CALENDARIFIC_ENABLED="true"
```

Both sources auto-populate on first access. Duplicate events are automatically deduplicated with UN taking priority.

### Timezone Modes

- **Timezone-aware** (default): Celebrates at 9 AM per user's timezone
- **Simple mode**: Single daily check at 10 AM server time

Toggle with `admin timezone enable/disable`.

## Project Structure

```text
brightdaybot/
├── app.py                  # Entry point
├── config.py               # Configuration
├── personality_config.py   # Personality definitions
├── handlers/               # Command & event handlers
│   ├── slash_commands.py   # /birthday, /special-day
│   ├── modal_handlers.py   # Birthday form modal
│   ├── app_home.py         # App Home dashboard
│   └── event_handler.py    # DM & channel events
├── services/               # Business logic
│   ├── birthday.py         # Celebrations
│   ├── celebration.py      # Pipeline & validation
│   └── scheduler.py        # Background tasks
├── utils/                  # Utilities
│   ├── message_generator.py
│   ├── image_generator.py
│   ├── block_builder.py
│   ├── un_observances.py   # UN/WHO/UNESCO day scraper
│   └── calendarific_api.py # National holiday API
└── data/
    ├── storage/            # Birthday data, configs
    ├── logs/               # 9 component logs
    ├── backups/            # Auto backups
    └── cache/              # Images, profiles, special days
        ├── un_observances/ # UN days (weekly refresh)
        └── calendarific/   # Holidays (weekly refresh)
```

## Production Deployment

```bash
# systemd service
sudo nano /etc/systemd/system/brightdaybot.service
```

```ini
[Unit]
Description=BrightDayBot
After=network-online.target

[Service]
Type=simple
ExecStart=/path/to/venv/bin/python /path/to/app.py
WorkingDirectory=/path/to/brightdaybot
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now brightdaybot
```

## Troubleshooting

1. **Health check**: `admin status` in Slack
2. **Logs**: Check `data/logs/` (ai.log, birthday.log, etc.)
3. **Common issues**:
   - Missing API keys → Check `.env`
   - Image failures → Verify OpenAI key has image access
   - Timezone issues → User must set timezone in Slack profile

## License

See [LICENSE](LICENSE).
