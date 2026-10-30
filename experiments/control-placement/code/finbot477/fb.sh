#!/bin/zsh
# Runs a command in finbot-pr477 with the OpenRouter key from .env в корне исследования (never printed).
cd ${0:A:h:h:h}/finbot-pr477
export OPENAI_API_KEY=$(sed -nE 's/^[[:space:]]*OPENROUTER_API_KEY[[:space:]]*=[[:space:]]*"?([^"[:space:]]+).*/\1/p' ../.env)
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
exec "$@"
