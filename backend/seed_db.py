"""Create and populate the sample holdings database.

Run once with:   python seed_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "holdings.db"


def main() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE funds (
            fund_id      TEXT PRIMARY KEY,
            name         TEXT NOT NULL,
            type         TEXT NOT NULL,  -- 'hedge_fund' or 'pension_fund'
            aum_usd      INTEGER NOT NULL
        );

        CREATE TABLE holdings (
            fund_id      TEXT NOT NULL,
            ticker       TEXT NOT NULL,
            company_name TEXT NOT NULL,
            shares       INTEGER NOT NULL,
            value_usd    INTEGER NOT NULL,
            PRIMARY KEY (fund_id, ticker),
            FOREIGN KEY (fund_id) REFERENCES funds(fund_id)
        );
        """
    )

    cur.executemany(
        "INSERT INTO funds VALUES (?, ?, ?, ?)",
        [
            ("ACME-EQ",  "Acme Equity Long/Short",         "hedge_fund",   2_400_000_000),
            ("ACME-PEN", "Acme Municipal Pension Trust",   "pension_fund", 18_500_000_000),
        ],
    )

    cur.executemany(
        "INSERT INTO holdings VALUES (?, ?, ?, ?, ?)",
        [
            ("ACME-EQ",  "AAPL", "Apple Inc.",                  120_000,    24_600_000),
            ("ACME-EQ",  "MSFT", "Microsoft Corporation",        85_000,    36_125_000),
            ("ACME-EQ",  "XOM",  "Exxon Mobil Corporation",     310_000,    35_960_000),
            ("ACME-PEN", "AAPL", "Apple Inc.",                  980_000,   200_900_000),
            ("ACME-PEN", "MSFT", "Microsoft Corporation",       640_000,   272_000_000),
        ],
    )

    conn.commit()
    conn.close()
    print(f"Seeded {DB_PATH}")


if __name__ == "__main__":
    main()
