import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _get_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer in .env") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than 0 in .env")
    return value


@dataclass(frozen=True)
class Config:
    token: str
    staff_role_id: int
    db_path: str
    guild_id: int
    plex_alpha_url: str
    plex_omega_url: str
    plex_delta_url: str
    plex_probe_timeout_seconds: int
    plex_probe_interval_minutes: int


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")

    staff_channel_id = int(os.getenv("STAFF_CHANNEL_ID", "0"))
    if staff_channel_id <= 0:
        raise RuntimeError("Missing STAFF_CHANNEL_ID in .env")

    support_channel_id = int(os.getenv("SUPPORT_CHANNEL_ID", "0"))

    reports_channel_ids = _csv_ids(os.getenv("REPORTS_CHANNEL_IDS", "").strip())
    if not reports_channel_ids:
        legacy = os.getenv("REPORTS_CHANNEL_ID", "").strip()
        if legacy.isdigit():
            reports_channel_ids = [int(legacy)]
    if not reports_channel_ids:
        raise RuntimeError("Missing REPORTS_CHANNEL_IDS (or REPORTS_CHANNEL_ID) in .env")

    # old single list (fallback)
    staff_ping_user_ids = _csv_ids(os.getenv("STAFF_PING_USER_IDS", "").strip())

    # ✅ NEW split lists (fallback to old list if not set)
    tv_staff_ping_user_ids = _csv_ids(os.getenv("TV_STAFF_PING_USER_IDS", "").strip())
    vod_staff_ping_user_ids = _csv_ids(os.getenv("VOD_STAFF_PING_USER_IDS", "").strip())

    if not tv_staff_ping_user_ids:
        tv_staff_ping_user_ids = staff_ping_user_ids
    if not vod_staff_ping_user_ids:
        vod_staff_ping_user_ids = staff_ping_user_ids

    public_updates = _get_bool("PUBLIC_UPDATES", True)
    db_path = os.getenv("DB_PATH", "./data/reports.sqlite3").strip()
    tmdb_bearer_token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    plex_alpha_url = os.getenv("PLEX_ALPHA_URL", "").strip()
    plex_omega_url = os.getenv("PLEX_OMEGA_URL", "").strip()
    plex_delta_url = os.getenv("PLEX_DELTA_URL", "").strip()
    configured_plex_urls = [plex_alpha_url, plex_omega_url, plex_delta_url]
    configured_plex_url_count = sum(1 for value in configured_plex_urls if value)
    if configured_plex_url_count not in (0, len(configured_plex_urls)):
        raise RuntimeError(
            "PLEX_ALPHA_URL, PLEX_OMEGA_URL, and PLEX_DELTA_URL must either all be set or all be omitted in .env"
        )

    plex_probe_timeout_seconds = _get_positive_int("PLEX_PROBE_TIMEOUT_SECONDS", 15)
    plex_probe_interval_minutes = _get_positive_int("PLEX_PROBE_INTERVAL_MINUTES", 5)

    staff_role_id = int(os.getenv("STAFF_ROLE_ID", "0"))
    if staff_role_id <= 0:
        raise RuntimeError("Missing STAFF_ROLE_ID in .env")

    db_path = os.getenv("DB_PATH", "./data/plex_liveboard.sqlite3").strip()
    guild_id = int(os.getenv("GUILD_ID", "0"))

    return Config(
        token=token,
        staff_role_id=staff_role_id,
        db_path=db_path,
        guild_id=guild_id,
        plex_alpha_url=plex_alpha_url,
        plex_omega_url=plex_omega_url,
        plex_delta_url=plex_delta_url,
        plex_probe_timeout_seconds=plex_probe_timeout_seconds,
        plex_probe_interval_minutes=plex_probe_interval_minutes,
    )
