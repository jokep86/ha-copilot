# HA Copilot

> Full Home Assistant administration co-pilot via Telegram, powered by Claude AI.

Control, monitor, and administer your entire Home Assistant installation from Telegram using natural language. No more fumbling with the HA UI — just tell it what you want.

## What it does

- **Device Control** — Turn on/off and configure any device with natural language
- **Automation CRUD** — Create, edit, delete automations from Telegram
- **Dashboard Management** — Lovelace CRUD with AI layout suggestions
- **Log Analysis** — Real-time logs with AI-powered diagnosis
- **System Administration** — Add-on management, backups, restarts
- **Proactive Alerts** — Get notified of problems before you notice them
- **AI Documentation** — Ask what any automation, entity, or integration does

## Installation

### Prerequisites
- Home Assistant OS or Supervised
- A Telegram bot token (from [@BotFather](https://t.me/botfather))
- An Anthropic API key

### Add-on installation

1. Add this repository to HA Supervisor:
   ```
   https://github.com/jokep86/ha-copilot
   ```
2. Install **HA Copilot** from the add-on store
3. Configure (see below)
4. Start the add-on

### Configuration

```yaml
telegram_bot_token: "your_bot_token"
allowed_telegram_ids:
  - 123456789   # your Telegram user ID
anthropic_api_key: "your_anthropic_api_key"
ai_model: "claude-sonnet-4-20250514"
log_level: "info"
```

Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot).

## Usage

Once running, open your Telegram bot and:

```
/start       — onboarding
/help        — full command reference
/sys         — system health dashboard
/devices     — list and control devices
```

Or just type naturally:
```
turn on the living room light
what's the temperature in the bedroom?
create an automation that turns off all lights at midnight
why is zigbee2mqtt showing errors?
```

## Architecture

```
Telegram Bot ──► Auth Middleware ──► Command Router
                                          │
                              ┌───────────┴───────────┐
                         Structured              NL Text / Voice
                         Commands               (Claude AI Engine)
                              │                       │
                         Module Handler          AIAction Schema
                              │                       │
                         HA REST API / Supervisor API / WebSocket
```

See [CLAUDE.md](CLAUDE.md) for the full engineering spec and architecture.

## Implementation Status

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Foundation — bot boots, /start and /help work | ✅ Complete |
| 2 | Device control via NL | 🔄 Next |
| 3 | System admin + power tools | ⏳ Planned |
| 4 | Automation/Scene CRUD + scheduling | ⏳ Planned |
| 5 | Proactive alerts + notifications | ⏳ Planned |
| 6 | Config + Dashboard management | ⏳ Planned |
| 7 | Media + Energy + Snapshots | ⏳ Planned |
| 8 | Migration assistant + open source | ⏳ Planned |

## Cost estimate

~$9–25/month for typical home use (~100 NL queries/day).
Configure `ai_daily_token_budget` to cap spending.

## License

Apache 2.0
