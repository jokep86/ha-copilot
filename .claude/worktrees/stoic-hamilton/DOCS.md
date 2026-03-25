# HA Copilot — User Documentation

## Getting Started

After installation (see [deploy.md](deploy.md)), open your Telegram bot and send `/start`.

HA Copilot understands natural language in any language. You can also use structured commands.

---

## Natural Language

Just type what you want:

| What you type | What happens |
|---------------|--------------|
| `turn on the living room light` | Turns on `light.living_room` |
| `what's the temperature?` | Gets sensor state |
| `dim the kitchen to 50%` | Sets brightness to 50% |
| `turn off all lights` | Calls `light.turn_off` for all lights |
| `turn off the lights in 30 minutes` | Creates a one-shot automation |
| `create an automation that turns on the porch light at sunset` | Generates automation YAML for your approval |

---

## Command Reference

### Devices
| Command | Description |
|---------|-------------|
| `/devices` | List all devices with inline control buttons |
| `/devices light` | List only light entities |
| `/status light.sala` | Show current state and attributes |
| `/entities` | Paginated list of all entities |
| `/history sensor.temp 24` | State history for last 24 hours |

### Automations
| Command | Description |
|---------|-------------|
| `/auto` | List automations |
| `/auto <id> on` | Enable automation |
| `/auto <id> off` | Disable automation |
| `/auto <id> trigger` | Manually trigger |
| `/auto <id> show` | Show YAML |
| `/auto <id> delete` | Delete (with confirmation) |

### Scenes
| Command | Description |
|---------|-------------|
| `/scenes` | List scenes |
| `/scene <id> activate` | Activate scene |
| `/scene <id> delete` | Delete (with confirmation) |

### System
| Command | Description |
|---------|-------------|
| `/sys` | System health dashboard |
| `/addons` | List add-ons with status |
| `/addon <slug> restart` | Restart add-on |
| `/logs` | HA Core logs (last 100 lines) |
| `/logs analyze` | AI diagnosis of recent errors |
| `/backup create` | Create full backup |
| `/backup list` | List available backups |
| `/restart core` | Restart HA Core (with confirmation) |
| `/reboot` | Host reboot (requires PIN) |

### AI Tools
| Command | Description |
|---------|-------------|
| `/explain auto <id>` | AI explains an automation |
| `/explain entity <id>` | AI explains an entity |
| `/template {{ states('sensor.temp') }}` | Evaluate Jinja2 template |
| `/raw GET /api/states/light.sala` | Direct API call |

### Media & Data
| Command | Description |
|---------|-------------|
| `/camera garage` | Camera snapshot |
| `/chart sensor.temp 48` | History chart (PNG) |
| `/export automations` | Export as YAML file |
| `/snapshot save before_update` | Save entity state snapshot |
| `/snapshot diff before_update` | Compare with current state |
| `/energy today` | Today's energy consumption |

### Alerts & Monitoring
| Command | Description |
|---------|-------------|
| `/alerts` | Active and recent alerts |
| `/notify on` | Enable proactive notifications |
| `/subs` | List active event subscriptions |
| `/schedule list` | Pending scheduled commands |
| `/audit stats` | AI token usage summary |
| `/audit cost` | Monthly cost estimate |

---

## Confirmation Levels

HA Copilot uses tiered confirmation to prevent accidents:

| Level | Actions | Confirmation |
|-------|---------|--------------|
| None | Read operations (get state, list) | Immediate |
| Single click | Toggle devices, activate scenes | ✅ button |
| Double confirm | Create/edit automations, edit config | Preview → "Are you sure?" |
| Password | Delete automations, restart, reboot | PIN code |

---

## Entity Aliases

In the add-on config, map friendly names to entity IDs:
```yaml
entity_aliases:
  "living room light": "light.living_room_main"
  "sala": "light.living_room_main"
  "temperatura": "sensor.living_room_temperature"
```

Claude will resolve aliases before executing commands.

---

## Quick Actions

Define personal shortcuts in config:
```yaml
quick_actions:
  - name: "Good Night"
    actions:
      - service: light.turn_off
        target:
          area_id: all
      - service: alarm_control_panel.arm_away
        target:
          entity_id: alarm_control_panel.home
```

Access with `/quick` — shows inline buttons for each action.

---

## Privacy & Security

- Only authorized Telegram user IDs (from config) can interact with the bot
- All unauthorized attempts are logged with user ID and timestamp
- The Supervisor token is never logged or exposed
- All AI actions are logged to the audit log (`/audit export`)
- Destructive operations require explicit confirmation
