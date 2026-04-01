# Plex Liveboard Bot

A stripped-down Discord bot that only maintains the Plex liveboard.

## What it does
- Creates a Plex status board with slash commands
- Watches Plex webhook log messages and updates server status automatically
- Stores liveboard location and current statuses in SQLite

## Required `.env`
```bash
DISCORD_TOKEN=your_bot_token
STAFF_ROLE_ID=123456789012345678
GUILD_ID=1457559352717086917
DB_PATH=./data/plex_liveboard.sqlite3
```

## Run
```bash
docker compose up -d --build
```
