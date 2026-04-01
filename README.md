# Plex Liveboard Bot

This project now contains only the Plex liveboard feature.

## Features
- Monitors Plex webhook log messages in the configured logs channel
- Tracks server state for Omega, Alpha, and Delta
- Posts and refreshes a liveboard embed in a chosen channel
- Stores liveboard config and statuses in SQLite

## Slash Commands
- `/plexliveboardstart`
- `/plexliveboardrefresh`
- `/plexliveboardstop`
- `/plexset`
- `/plexstatus`
- `/plexclear`

All commands are staff-only and require `STAFF_ROLE_ID`.

## Setup

### 1. Create environment file
```bash
cp .env.example .env
```

### 2. Set required values in `.env`
- `DISCORD_TOKEN`
- `STAFF_ROLE_ID`

Optional values:
- `DB_PATH` (defaults to `./data/plex_liveboard.sqlite3`)
- `GUILD_ID` (set for faster per-guild command sync during development)

### 3. Run with Docker
```bash
docker compose up -d --build
```

## Notes
- Do not commit your `.env` file
- Runtime data is stored in `./data` via Docker volume
