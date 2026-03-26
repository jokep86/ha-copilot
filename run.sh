#!/usr/bin/with-contenv bashio
set -e

# In local dev (HA_OPTIONS_PATH set), bashio supervisor calls will fail — skip them.
if bashio::var.has_value "${HA_OPTIONS_PATH:-}"; then
  echo "[INFO] Local dev mode — skipping bashio supervisor calls"
  export LOG_LEVEL="${LOG_LEVEL:-info}"
else
  bashio::log.info "Starting HA Copilot v$(bashio::addon.version)..."
  export LOG_LEVEL="$(bashio::config 'log_level')"
fi

cd /app
exec python3 -m app.main
