"""Import a fund's holdings from a CSV upload.

Accepts a header row and tolerates several common column-name variants
(``ticker``/``symbol``, ``shares``/``quantity``). Replaces the named fund's
existing holdings on import.

Position value is intentionally NOT stored — it changes with the market price
every day. The recommender doesn't need it; the UI shows shares only.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "holdings.db"


_TICKER_KEYS  = {"ticker", "symbol"}
_SHARES_KEYS  = {"shares", "quantity", "qty", "units"}
_NAME_KEYS    = {"company_name", "company", "name", "description"}


def _pick_column(headers: list[str], aliases: set[str]) -> str | None:
    for h in headers:
        if h.lower().replace(" ", "_") in aliases:
            return h
    return None


def _parse_int(value: str) -> int:
    """Strip $ , and whitespace, then int-cast."""
    s = (value or "").strip().replace("$", "").replace(",", "").replace("_", "")
    if not s:
        raise ValueError("empty number")
    return int(float(s))


def import_csv(fund_id: str, csv_bytes: bytes) -> dict:
    """Parse and ingest. Replaces all existing holdings for fund_id.

    Returns {"fund_id": ..., "rows_inserted": N, "rows_skipped": M, "errors": [...]}.
    """
    text = csv_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row.")

    ticker_col = _pick_column(reader.fieldnames, _TICKER_KEYS)
    shares_col = _pick_column(reader.fieldnames, _SHARES_KEYS)
    name_col   = _pick_column(reader.fieldnames, _NAME_KEYS)

    missing = [n for n, v in [("ticker", ticker_col), ("shares", shares_col)] if v is None]
    if missing:
        raise ValueError(
            f"CSV is missing required column(s): {', '.join(missing)}. "
            f"Headers seen: {reader.fieldnames}. "
            "Accepted aliases — ticker/symbol, shares/quantity."
        )

    rows = []
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):  # row 1 = header
        try:
            ticker = (row[ticker_col] or "").strip().upper()
            if not ticker:
                continue
            shares = _parse_int(row[shares_col])
            company = (row[name_col].strip() if name_col and row.get(name_col) else ticker)
            rows.append((fund_id, ticker, company, shares))
        except Exception as e:
            errors.append(f"Row {i}: {e}")

    if not rows:
        raise ValueError(f"No valid rows parsed. Errors: {errors[:5]}")

    with sqlite3.connect(DB_PATH) as conn:
        owner = conn.execute("SELECT 1 FROM funds WHERE fund_id = ?", (fund_id,)).fetchone()
        if not owner:
            raise ValueError(f"Fund {fund_id!r} does not exist; create it first.")
        conn.execute("DELETE FROM holdings WHERE fund_id = ?", (fund_id,))
        conn.executemany(
            "INSERT INTO holdings (fund_id, ticker, company_name, shares) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    return {
        "fund_id": fund_id,
        "rows_inserted": len(rows),
        "rows_skipped": len(errors),
        "errors": errors[:20],
    }
