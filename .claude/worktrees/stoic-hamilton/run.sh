#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting HA Copilot v$(bashio::addon.version)..."

# Export log level for Python
export LOG_LEVEL="$(bashio::config 'log_level')"

cd /app
exec python3 -m app.main
