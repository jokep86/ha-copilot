# Deployment Guide

Single source of truth for provisioning, validation, maintenance, and rollback.

---

## Prerequisites

- Home Assistant OS or Supervised (Proxmox VM or bare metal)
- Supervisor version 2024.x or later
- A Telegram bot token — create one via [@BotFather](https://t.me/botfather)
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)
- Your Telegram user ID — get it from [@userinfobot](https://t.me/userinfobot)

---

## Installation

### 1. Add the repository to Supervisor

In HA → Settings → Add-ons → Add-on store → ⋮ → Repositories:
```
https://github.com/pedro/ha-copilot
```

### 2. Install the add-on

Find **HA Copilot** in the store and click **Install**.

### 3. Configure

In the add-on **Configuration** tab, set at minimum:
```yaml
telegram_bot_token: "1234567890:ABCdef..."
allowed_telegram_ids:
  - 123456789        # your Telegram user ID
anthropic_api_key: "sk-ant-..."
```

### 4. Start

Click **Start**. Watch the **Log** tab for the startup self-test report.

### 5. Validate

Open your Telegram bot and send `/start`. You should receive:
```
👋 Welcome to HA Copilot v0.1.0!
```

Then check `/sys` for full component health.

---

## Configuration Reference

| Option | Default | Description |
|--------|---------|-------------|
| `telegram_bot_token` | — | **Required.** From @BotFather |
| `allowed_telegram_ids` | — | **Required.** List of authorized user IDs |
| `anthropic_api_key` | — | **Required.** Anthropic API key |
| `ai_model` | `claude-sonnet-4-20250514` | Claude model |
| `ai_daily_token_budget` | `500000` | Daily token cap |
| `chat_mode` | `both` | `private`, `group`, or `both` |
| `log_level` | `info` | `debug`, `info`, `warning`, `error` |
| `health_pulse_interval_seconds` | `300` | Heartbeat interval |
| `dead_man_switch_timeout_seconds` | `600` | Watchdog timeout |
| `db_purge_days` | `90` | Log retention period |

Full option reference: see `config.yaml` schema section.

---

## Validation

After starting, verify:

1. **Startup report** in Telegram — all 🟢 indicators
2. **`/start`** responds with welcome message
3. **`/help`** shows full command list
4. **`/sys`** shows component health dashboard
5. **Add-on logs** in Supervisor show no ERROR or CRITICAL lines

---

## Maintenance

### Log files

Logs are written to `/data/logs/ha_copilot.log` inside the add-on.
Access via Supervisor → HA Copilot → Log tab, or via the file editor add-on at `/addon_configs/ha-copilot/`.

### Database

SQLite DB at `/data/ha_copilot.db`. Included in HA backups automatically.
- Old records purged automatically per `db_purge_days`
- VACUUM runs weekly
- Size alert if > 500 MB

### Updates

When a new version is available:
1. Supervisor will show an update badge
2. Review `CHANGELOG.md` for breaking changes
3. Click **Update** in the add-on store
4. Monitor the log for successful startup

---

## Rollback

If an update causes issues:

1. In Supervisor → HA Copilot → click **Stop**
2. Go to **Info** tab → select previous version from the dropdown
3. Click **Install** then **Start**
4. Alternatively, restore from a full HA backup

---

## Troubleshooting

### Bot not responding
- Check `allowed_telegram_ids` includes your user ID
- Verify `telegram_bot_token` is correct
- Check Supervisor logs for AUTH errors

### Claude not working
- Verify `anthropic_api_key` is valid
- Check `/sys` — Claude component should be 🟢
- Check `ai_daily_token_budget` hasn't been exhausted

### HA API errors
- Ensure `hassio_api: true` and `homeassistant_api: true` in add-on config
- Check that `hassio_role: admin` is set
- Verify SUPERVISOR_TOKEN is being injected (check Supervisor logs)

### Database errors
- Check `/data/` is writable (mapped in `config.yaml`)
- Check available disk space
- If corrupted: stop add-on, delete `/data/ha_copilot.db`, restart (data loss but add-on recovers)
