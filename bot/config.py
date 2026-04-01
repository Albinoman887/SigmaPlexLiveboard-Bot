import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    token: str
    staff_role_id: int
    db_path: str
    guild_id: int


def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in .env")

    staff_role_id = int(os.getenv("STAFF_ROLE_ID", "0"))
    if staff_role_id <= 0:
        raise RuntimeError("Missing STAFF_ROLE_ID in .env")

    db_path = os.getenv("DB_PATH", "./data/plex_liveboard.sqlite3").strip()
    guild_id = int(os.getenv("GUILD_ID", "1457559352717086917"))

    return Config(
        token=token,
        staff_role_id=staff_role_id,
        db_path=db_path,
        guild_id=guild_id,
    )
