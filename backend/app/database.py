"""Read-only access to the holdings database."""

import sqlite3
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).parent.parent / "data" / "holdings.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_funds() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT fund_id, name, type, aum_usd FROM funds ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def list_holdings(fund_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ticker, company_name, shares, value_usd
            FROM holdings
            WHERE fund_id = ?
            ORDER BY value_usd DESC
            """,
            (fund_id,),
        ).fetchall()
    return [dict(r) for r in rows]
