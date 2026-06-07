import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "roliwatch.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tracked_items (
                item_id     INTEGER NOT NULL,
                guild_id    INTEGER NOT NULL,
                added_by    INTEGER NOT NULL,
                last_value  INTEGER,
                last_rap    INTEGER,
                PRIMARY KEY (item_id, guild_id)
            );

            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id    INTEGER PRIMARY KEY,
                channel_id  INTEGER
            );
        """)


def set_alert_channel(guild_id: int, channel_id: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO guild_settings (guild_id, channel_id) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, channel_id),
        )


def get_alert_channel(guild_id: int) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
    return row["channel_id"] if row else None


def add_tracked_item(item_id: int, guild_id: int, added_by: int):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tracked_items (item_id, guild_id, added_by)"
            " VALUES (?, ?, ?)",
            (item_id, guild_id, added_by),
        )


def remove_tracked_item(item_id: int, guild_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM tracked_items WHERE item_id = ? AND guild_id = ?",
            (item_id, guild_id),
        )
    return cur.rowcount > 0


def get_tracked_items(guild_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM tracked_items WHERE guild_id = ?", (guild_id,)
        ).fetchall()


def get_all_tracked_items() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM tracked_items").fetchall()


def update_item_prices(item_id: int, guild_id: int, value: int | None, rap: int | None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE tracked_items SET last_value = ?, last_rap = ?"
            " WHERE item_id = ? AND guild_id = ?",
            (value, rap, item_id, guild_id),
        )
