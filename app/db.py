import os
import sqlite3
from datetime import datetime
from typing import Optional, Tuple

from .config import settings


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.db_path) or ".", exist_ok=True)
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS rebilled (
                buyid INTEGER PRIMARY KEY,
                invoiceid INTEGER NOT NULL,
                invoice_number TEXT,
                rebilled_at TEXT NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def get_setting(key: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_credentials() -> tuple[Optional[str], Optional[str]]:
    """Cl\u00e9s API : SQLite d'abord, puis .env en fallback."""
    pk = get_setting("evoliz_public_key") or settings.evoliz_public_key
    sk = get_setting("evoliz_secret_key") or settings.evoliz_secret_key
    return pk, sk


def has_credentials() -> bool:
    pk, sk = get_credentials()
    if not (pk and sk):
        return False
    return "PLACEHOLDER" not in (pk + sk)


def is_rebilled(buyid: int) -> bool:
    with _conn() as c:
        cur = c.execute("SELECT 1 FROM rebilled WHERE buyid = ?", (buyid,))
        return cur.fetchone() is not None


def rebilled_set() -> set[int]:
    with _conn() as c:
        return {row["buyid"] for row in c.execute("SELECT buyid FROM rebilled")}


def mark_rebilled(buyid: int, invoiceid: int, invoice_number: Optional[str]) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO rebilled (buyid, invoiceid, invoice_number, rebilled_at) "
            "VALUES (?, ?, ?, ?)",
            (buyid, invoiceid, invoice_number, datetime.utcnow().isoformat()),
        )


def list_rebilled() -> list[sqlite3.Row]:
    with _conn() as c:
        return list(
            c.execute(
                "SELECT buyid, invoiceid, invoice_number, rebilled_at "
                "FROM rebilled ORDER BY rebilled_at DESC"
            )
        )
