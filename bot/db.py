import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReportDB:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plex_liveboards (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plex_statuses (
                guild_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, server_name)
            )
            """
        )

        self.conn.commit()

    def set_plex_liveboard(self, guild_id: int, channel_id: int, message_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO plex_liveboards (guild_id, channel_id, message_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id)
            DO UPDATE SET channel_id=excluded.channel_id,
                          message_id=excluded.message_id
            """,
            (int(guild_id), int(channel_id), int(message_id)),
        )
        self.conn.commit()

    def get_plex_liveboard(self, guild_id: int) -> Optional[dict]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT guild_id, channel_id, message_id FROM plex_liveboards WHERE guild_id=?",
            (int(guild_id),),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "guild_id": row["guild_id"],
            "channel_id": row["channel_id"],
            "message_id": row["message_id"],
        }

    def list_plex_liveboards(self) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT guild_id, channel_id, message_id FROM plex_liveboards")
        rows = cur.fetchall()
        return [
            {"guild_id": r["guild_id"], "channel_id": r["channel_id"], "message_id": r["message_id"]}
            for r in rows
        ]

    def clear_plex_liveboard(self, guild_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM plex_liveboards WHERE guild_id=?", (int(guild_id),))
        self.conn.commit()

    def set_plex_status(self, guild_id: int, server_name: str, status: str, updated_at: Optional[str] = None) -> None:
        now = updated_at or _utcnow_iso()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO plex_statuses (guild_id, server_name, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, server_name)
            DO UPDATE SET status=excluded.status,
                          updated_at=excluded.updated_at
            """,
            (int(guild_id), str(server_name).upper(), str(status), now),
        )
        self.conn.commit()

    def get_plex_statuses(self, guild_id: int) -> dict[str, str]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT server_name, status FROM plex_statuses WHERE guild_id=?",
            (int(guild_id),),
        )
        rows = cur.fetchall()
        return {
            str(r["server_name"]).upper(): str(r["status"])
            for r in rows
            if r["server_name"] is not None and r["status"] is not None
        }

    def clear_plex_statuses(self, guild_id: int) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM plex_statuses WHERE guild_id=?", (int(guild_id),))
        self.conn.commit()
