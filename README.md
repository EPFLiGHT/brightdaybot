# BrightDayBot

A Slack bot that records and wishes workspace members happy birthday with AI-generated personalized messages and images.

## ✨ Key Features

- **🎯 AI-Generated Messages**: Personalized birthday wishes using OpenAI GPT-4.1
- **🖼️ AI Birthday Images**: Face-accurate images using your Slack profile photo and GPT-Image-1
- **🌍 Multi-Timezone Support**: Celebrates birthdays at 9 AM by default in each user's local timezone (configurable)
- **🎭 8 Unique Personalities**: From mystic dog to superhero to pirate themes
- **📈 Smart Consolidation**: Single message for multiple birthdays to avoid spam
- **🔧 Dynamic Configuration**: Change AI models and settings without restart
- **📊 Admin Management**: User management, statistics, and system health monitoring
- **💾 Automatic Backups**: Data protection with automated backup system

## 🚀 Quick Setup

### 1. Create Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps) → "Create New App"
2. Enable **Socket Mode** (App-Level Tokens → Generate Token with `connections:write` scope)
3. Configure **Event Subscriptions**:

   - Navigate to "Event Subscriptions" in your app settings
   - Toggle "Enable Events" to ON
   - Note: "Socket Mode is enabled. You won't need to specify a Request URL."

   **Subscribe to Bot Events** (required for bot functionality):

   ```plaintext
   app_mention              # Subscribe to messages that mention @brightdaybot
   member_joined_channel    # Detect when users join channels (for welcome messages)
   message.channels         # Listen to messages posted in channels
   message.im               # Listen to direct messages sent to the bot
   ```

   _Note: Slack automatically adds the necessary OAuth scopes when you add these events. The Bot Token Scopes below ensure all permissions are properly configured._

4. Add **Bot Token Scopes** (OAuth & Permissions → Scopes → Bot Token Scopes):

   **Core Messaging & Communication:**

   ```plaintext
   chat:write                 # Send messages as brightdaybot
   chat:write.public          # Send messages to channels bot isn't member of
   chat:write.customize       # Send messages with custom username/avatar
   im:write                   # Start direct messages with people
   im:read                    # View basic DM information
   im:history                 # View messages in direct messages
   app_mentions:read          # View messages that mention @brightdaybot
   ```

   **Channel & Group Access:**

   ```plaintext
   channels:read              # View basic information about public channels
   channels:history           # View messages in public channels
   channels:manage            # Manage public channels and create new ones
   channels:write.invites     # Invite members to public channels
   groups:read                # View basic information about private channels
   mpim:read                  # View basic info about group direct messages
   ```

   **User & Workspace Information:**

   ```plaintext
   users:read                 # View people in workspace
   users.profile:read         # View profile details about people
   emoji:read                 # View custom emoji in workspace
   ```

   **File & Content Management:**

   ```plaintext
   files:write                # Upload, edit and delete files
   files:read                 # View files shared in channels/conversations
   reactions:read             # View emoji reactions and content
   ```

5. Install app to workspace and copy both tokens:
   - **Bot User OAuth Token** (`xoxb-...`)
   - **App-Level Token** (`xapp-...`) with `connections:write` scope

### 2. Install & Configure

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env  # Edit with your tokens and keys
```

**Required environment variables:**

```env
SLACK_BOT_TOKEN="xoxb-your-bot-token"
SLACK_APP_TOKEN="xapp-your-app-token"
BIRTHDAY_CHANNEL_ID="C0123456789"
OPENAI_API_KEY="sk-your-openai-api-key"
```

**Optional configuration variables:**

```env
# AI & Message Settings
OPENAI_MODEL="gpt-4.1"  # Override default AI model
AI_IMAGE_GENERATION_ENABLED="true"  # Enable/disable image generation
USE_CUSTOM_EMOJIS="true"  # Use custom workspace emojis

# Web Search & Caching
WEB_SEARCH_CACHE_ENABLED="true"  # Cache historical date facts

# Backup System Configuration
EXTERNAL_BACKUP_ENABLED="true"  # Enable external backup system
BACKUP_TO_ADMINS="true"  # Send backup files to admin users via DM
BACKUP_CHANNEL_ID="C0987654321"  # Optional: dedicated backup channel ID
BACKUP_ON_EVERY_CHANGE="true"  # Send backup on every change vs. batched

# Custom Bot Personality (when using 'custom' personality)
CUSTOM_BOT_NAME="Birthday Wizard"
CUSTOM_BOT_DESCRIPTION="a magical birthday celebration wizard"
CUSTOM_BOT_STYLE="magical, whimsical, and full of enchantment"
CUSTOM_FORMAT_INSTRUCTION="Create a magical spell-like birthday message"
CUSTOM_BOT_TEMPLATE_EXTENSION="Your custom template extension here"
```

### 3. Run the Bot

```bash
python app.py
```

## 🎮 Usage

### Welcome Experience

**New User Onboarding**: When users join your workspace:

1. **Automatic Birthday Channel Access**: New members are automatically added to the birthday channel
2. **Single Welcome Message**: Users receive one comprehensive welcome message in the birthday channel (no team-wide notifications)
3. **Clear Instructions**: Welcome message includes birthday setup instructions and available commands
4. **Opt-out Information**: Instructions on how to leave the birthday channel if desired
5. **Profile Optimization**: Recommendations to set timezone and profile photo for better personalization

**Note**: The bot only sends birthday channel welcome messages - no duplicate team-wide notifications to prevent spam.

### User Commands (DM the bot)

- `add DD/MM` or `add DD/MM/YYYY` - Set your birthday
- `check` - View your saved birthday
- `remove` - Remove your birthday
- `test [quality] [size] [--text-only]` - See a sample birthday message with image (--text-only skips image generation)
- `help` - Show all commands

### Admin Commands

**Basic Admin Commands:**

- `admin help` - Complete admin command reference with all personalities
- `admin list` / `admin add USER_ID` / `admin remove USER_ID` - Manage admin users
- `list` / `list all` - View upcoming birthdays / all birthdays by month
- `stats` - Birthday statistics and system overview
- `admin status` / `admin status detailed` - Comprehensive health check monitoring 20+ components (API parameters, image generation, logging, testing infrastructure)
- `config` / `config COMMAND true/false` - View and change command permissions

**Bot Personality Management:**

- `admin personality [name]` - Change bot personality (standard, mystic_dog, poet, etc.)
- `admin custom name [value]` - Set custom personality name
- `admin custom description [value]` - Set custom personality description
- `admin custom style [value]` - Set custom writing style
- `admin custom format [value]` - Set custom formatting instructions
- `admin custom template [value]` - Set additional template instructions

**Testing & Debugging:**

- `admin test @user [quality] [size] [--text-only]` - Generate test birthday message & image (stays in DM)
- `admin test-join [@user]` - Test birthday channel welcome message flow
- `admin test-upload` - Test image upload functionality
- `admin test-file-upload` - Test text file upload functionality
- `admin test-external-backup` - Test external backup system with diagnostics
- `admin test-bot-celebration [quality] [size] [--text-only]` - Test BrightDayBot's self-celebration (Ludo's mystical birthday message)

**Data Management:**

- `admin backup` - Create manual backup of birthday data
- `admin restore latest` - Restore from the latest backup
- `admin cache clear` - Clear all web search cache
- `admin cache clear DD/MM` - Clear web search cache for specific date

**Mass Notification Commands** (require confirmation):

- `admin announce [message]` - Send custom announcement to birthday channel
- `admin announce image` - Announce AI image generation feature
- `remind` / `remind new` - Send reminders to users without birthdays
- `remind update` - Send profile update reminders to users with birthdays
- `remind new [message]` - Send custom reminder to new users
- `remind update [message]` - Send custom profile update reminder
- `confirm` - Confirm pending mass notification (5-minute timeout)

### 🤖 OpenAI Model Management

**Dynamic Model Configuration** (NEW): Change AI models without restarting the bot.

**Available Commands:**

- `admin model` - Show current model and configuration source
- `admin model list` - List all supported OpenAI models
- `admin model set <model>` - Change to specified model (e.g., `admin model set gpt-4o`)
- `admin model reset` - Reset to default model (gpt-4.1)

**Supported Models:**

- `gpt-4.1` (default), `gpt-4o`, `gpt-4o-mini`, `gpt-4`, `gpt-4-turbo`
- `gpt-5`, `gpt-5-mini`

**Configuration Priority:**

1. File-based setting (highest) - `data/storage/openai_model_settings.json`
2. Environment variable `OPENAI_MODEL` (fallback)
3. Default model `gpt-4.1` (final fallback)

### Bot Personalities

Choose from 8 unique personalities:

- `standard` - Friendly default bot
- `mystic_dog` - Ludo the cosmic fortune-teller
- `poet` - Lyrical verse creator
- `tech_guru` - Programming-themed messages
- `chef` - Culinary birthday celebrations
- `superhero` - Comic book style messages
- `time_traveler` - Sci-fi themed wishes
- `pirate` - Nautical adventure messages

## 🛠️ System Service (Production)

Create systemd service for auto-restart:

```bash
sudo nano /etc/systemd/system/brightdaybot.service
```

```ini
[Unit]
Description=BrightDayBot Service
After=network-online.target

[Service]
Type=simple
ExecStart=/path/to/venv/bin/python /path/to/brightdaybot/app.py
WorkingDirectory=/path/to/brightdaybot
User=your_username
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable brightdaybot.service
sudo systemctl start brightdaybot.service
```

## 🎨 Customization

### AI Image Generation

- **Reference Photos**: Uses Slack profile photos for face-accurate images
- **Quality Control**: Low/medium/high/auto settings for cost optimization
- **Personality Themes**: Each bot personality generates images in its unique style
- **Smart Fallback**: Text-only generation when no profile photo available

### Configuration Options

- **Timezone Modes**: Timezone-aware (default) or simple daily announcements
- **Image Settings**: Enable/disable AI image generation
- **Custom Personalities**: Create your own bot personality
- **OpenAI Models**: Switch between GPT models via admin commands

## 🎯 Advanced Usage Examples

### Command Examples with Parameters

```bash
# Test birthday messages with specific quality and size
test low 1024x1024          # Low quality, square image
admin test @john high auto  # High quality, auto-sized for specific user

# Cache management for specific dates
admin cache clear 25/12     # Clear Christmas cache
admin cache clear           # Clear all cached data

# Custom personality configuration
admin custom name "Birthday Wizard"
admin custom style "magical and whimsical"
admin custom template "Add magical sparkles and enchantments"

# Model management
admin model set gpt-4o      # Switch to GPT-4o
admin model list            # Show all available models
admin model                 # Show current model status
```

### Timezone Management

```bash
# Check current timezone mode
admin timezone

# Enable timezone-aware celebrations (9 AM by default, configurable via TIMEZONE_CELEBRATION_TIME)
admin timezone enable

# Disable for simple mode (10 AM by default, configurable via DAILY_CHECK_TIME)
admin timezone disable

# View detailed timezone schedule
admin timezone status
```

## 📁 Project Structure

```plaintext
brightdaybot/
├── app.py                    # Main entry point
├── config.py                 # Core configuration
├── personality_config.py     # Bot personality definitions
├── data/                     # Data storage
│   ├── logs/                 # Component-specific log files
│   ├── storage/              # Birthday data & settings
│   ├── cache/                # Web search & image cache
│   └── backups/              # Automatic data backups
├── handlers/                 # Slack event handlers
├── services/                 # Birthday & scheduling logic
└── utils/                    # Helper utilities
    ├── message_generator.py  # AI message generation
    ├── image_generator.py    # AI image generation
    ├── app_config.py         # Configuration management
    ├── logging_config.py     # Logging system
    └── [other utilities]
```

## 🏗️ Technical Architecture

### Modular Configuration System

**Recent Enhancement**: Config.py refactored from 544 to 174 lines by extracting functionality into focused utility modules:

- **`config.py`** - Core configuration constants, environment variables, and centralized OpenAI API parameters
- **`utils/app_config.py`** - Dynamic configuration management (OpenAI models, personalities, admin users)
- **`utils/logging_config.py`** - Multi-component logging system with 9 specialized log files
- **`utils/template_utils.py`** - Message template building and emoji management

### Core Components

- **Entry Point**: `app.py` - Initializes Slack app, registers handlers, starts scheduler
- **Event Handling**: `handlers/` - Processes Slack events (DMs, team joins) and user commands
- **Services**: `services/` - Birthday management logic and timezone-aware scheduling
- **Storage**: File-based system with automatic backups and JSON configuration
- **AI Integration**: OpenAI GPT-4.1 for messages, GPT-Image-1 for face-accurate birthday images

### Admin System

**Multi-Level Access Control**:

- **Workspace Admins**: Automatic admin privileges for Slack workspace admins
- **Configured Admins**: Stored in `data/storage/admins.json` with persistent settings
- **Command Permissions**: Granular control over which commands require admin access
- **Health Monitoring**: Comprehensive system diagnostics via `admin status`

## 📊 Data Management

### File Storage Structure

All data stored in organized `data/` directory:

- **`storage/birthdays.txt`** - Birthday data (format: `user_id:DD/MM/YYYY`)
- **`storage/*.json`** - Configuration files (admins, personality, permissions, timezone, model settings)
- **`tracking/`** - Daily announcement tracking to prevent duplicates
- **`backups/`** - Automatic birthday data backups (maintains 10 most recent)
- **`cache/`** - Web search results and AI-generated images with auto-cleanup

### Enhanced Logging System

**9 Component-Specific Log Files** for targeted debugging:

- **`main.log`** - Core application startup and configuration
- **`commands.log`** - User commands and admin actions
- **`events.log`** - Slack events (DMs, team joins)
- **`birthday.log`** - Birthday service logic and celebrations
- **`ai.log`** - AI/LLM interactions (OpenAI API calls, image generation)
- **`slack.log`** - Slack API interactions and user profiles
- **`storage.log`** - Data storage operations and backups
- **`system.log`** - System utilities and health checks
- **`scheduler.log`** - Background scheduling tasks

**Logging Features**:

- **Automatic Rotation**: Files rotate at 10MB (keeping 5 backups)
- **Component Routing**: Each module logs to appropriate file
- **Health Monitoring**: Log status included in `admin status` command

### Data Protection

- **Automatic Backups**: Timestamped backups on each modification
- **Recovery System**: Auto-restoration from backups if data corrupted
- **File Locking**: Prevents corruption during concurrent operations
- **Cache Management**: Automatic cleanup (images: 30 days, profiles: 7 days)

### External Backup System

**Advanced Backup Protection**: Sends backup files to admin users and optionally to dedicated channels.

**Features**:

- **Admin DM Backups**: Backup files automatically sent to admin users via direct message
- **Dedicated Backup Channel**: Optional channel for centralized backup storage
- **Configurable Frequency**: Backup on every change or batched/daily
- **Testing**: Use `admin test-external-backup` to verify backup system functionality
- **Manual Control**: `admin backup` for on-demand backups

**Configuration**:

- `EXTERNAL_BACKUP_ENABLED="true"` - Enable the external backup system
- `BACKUP_TO_ADMINS="true"` - Send backup files to admin DMs
- `BACKUP_CHANNEL_ID="C0123456789"` - Optional backup channel
- `BACKUP_ON_EVERY_CHANGE="true"` - Frequency control

## 🔐 Confirmation System

**Mass Notification Safety**: Prevents accidental spam with two-step confirmation for commands that notify multiple users.

### Commands Requiring Confirmation

- `admin announce [message]` - Channel announcements
- `admin announce image` - Feature announcements
- `remind new [message]` - DM reminders to users without birthdays
- `remind update [message]` - DM reminders to users with birthdays

### How It Works

1. **Initial Command**: Run a mass notification command
2. **Preview & Request**: Bot shows message preview and user count
3. **Confirmation**: Type `confirm` within 5 minutes to proceed
4. **Execution**: Bot sends notifications and provides summary
5. **Timeout**: Confirmations expire after 5 minutes for safety

### Example Flow

```plaintext
You: admin announce Welcome to our new birthday system!

Bot: 📢 CONFIRMATION REQUIRED 📢
Preview of announcement to birthday channel:
"Welcome to our new birthday system!"
This will notify approximately 25 users in #birthdays.
Type `confirm` within 5 minutes to send.

You: confirm

Bot: ✅ Announcement sent successfully to the birthday channel!
```

## 🔧 Troubleshooting

### Quick Diagnostics

1. Run `admin status` in Slack for comprehensive health check
2. For detailed info: `admin status detailed`
3. Check component-specific logs in `data/logs/`:
   - `main.log` - Core application issues
   - `commands.log` - User command problems
   - `ai.log` - OpenAI API and image generation issues
   - `birthday.log` - Birthday service logic problems
   - Plus 5 other specialized log files
4. Verify environment variables and API keys
5. Ensure proper Slack permissions

### Common Issues

- **Missing API Keys**: Check `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `OPENAI_API_KEY`
- **Network Issues at Startup**: Use `network-online.target` and `RestartSec=30` in systemd service
- **Permission Errors**: Verify file/directory permissions for `data/` folder
- **Image Generation Problems**: Ensure OpenAI key has GPT-Image-1 access
- **Timezone Issues**: Users must set timezone in Slack profile settings
- **Model Configuration**: Use `admin model` to check current AI model status

## ⚙️ Important Implementation Details

### Timezone-Aware Celebrations

**Two Modes Available**:

1. **Timezone-Aware Mode** (default): Celebrates at 9 AM by default in each user's timezone (configurable)

   - Hourly checks to catch different timezone groups
   - Single consolidated message for all same-day birthdays
   - Enable: `admin timezone enable`

2. **Simple Mode**: Single daily check at 10 AM by default server time (configurable)
   - All birthdays announced together
   - Enable: `admin timezone disable`

### AI Features

- **Message Generation**: Uses OpenAI GPT with personality-specific prompts
- **Image Generation**: GPT-Image-1 with face-accurate reference photo mode
- **Web Search Integration**: Historical date facts cached for efficiency
- **Smart Consolidation**: Single message for multiple same-day birthdays
- **Natural Flow**: Images attached automatically (no "look at image" text)

### Security & Reliability

- **Socket Mode**: Secure Slack connectivity without webhooks
- **File Locking**: Prevents data corruption during concurrent operations
- **Input Validation**: Year range validation (1900-current year)
- **Startup Recovery**: Catches missed celebrations after downtime
- **Custom Emoji Support**: Adapts based on workspace emoji availability

## 🏗️ Architecture Highlights

**Recent Major Enhancement**: Config.py refactored from 544 to 174 lines by extracting functionality into focused utility modules:

- `utils/app_config.py` - Dynamic configuration management
- `utils/logging_config.py` - Multi-component logging system
- `utils/template_utils.py` - Message template building

This modular architecture improves maintainability while preserving all functionality through backward-compatible imports.

## 📜 License

See [LICENSE](LICENSE) for details.
