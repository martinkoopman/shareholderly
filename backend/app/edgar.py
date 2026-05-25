"""Discover and fetch DEF 14A filings from SEC EDGAR.

SEC rules: every request must include a User-Agent identifying the caller,
and we must stay under ~10 requests/second. See:
    https://www.sec.gov/os/accessing-edgar-data
"""

from __future__ import annotations

import httpx

from . import config


class EdgarError(Exception):
    pass


def _client() -> httpx.Client:
    if not config.SEC_USER_AGENT:
        raise EdgarError("SEC_USER_AGENT is not set in backend/.env")
    return httpx.Client(
        headers={
            "User-Agent": config.SEC_USER_AGENT,
            "Accept": "application/json, text/html",
        },
        timeout=30.0,
        follow_redirects=True,
    )


_ticker_to_cik_cache: dict[str, str] | None = None


def ticker_to_cik(ticker: str) -> str:
    """Return zero-padded 10-digit CIK for a ticker (e.g. AAPL → '0000320193')."""
    global _ticker_to_cik_cache
    if _ticker_to_cik_cache is None:
        with _client() as c:
            r = c.get("https://www.sec.gov/files/company_tickers.json")
            r.raise_for_status()
            mapping = r.json()
        _ticker_to_cik_cache = {
            row["ticker"].upper(): str(row["cik_str"]).zfill(10)
            for row in mapping.values()
        }
    cik = _ticker_to_cik_cache.get(ticker.upper())
    if not cik:
        raise EdgarError(f"No CIK found for ticker {ticker}")
    return cik


def latest_def14a(ticker: str) -> dict:
    """Return metadata + the primary document URL for the most recent DEF 14A."""
    cik = ticker_to_cik(ticker)
    with _client() as c:
        r = c.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
        r.raise_for_status()
        sub = r.json()

    recent = sub["filings"]["recent"]
    # Walk newest → oldest looking for DEF 14A.
    for i, form in enumerate(recent["form"]):
        if form == "DEF 14A":
            accession = recent["accessionNumber"][i]
            primary_doc = recent["primaryDocument"][i]
            filing_date = recent["filingDate"][i]
            acc_no_dashes = accession.replace("-", "")
            doc_url = (
                f"https://www.sec.gov/Archives/edgar/data/"
                f"{int(cik)}/{acc_no_dashes}/{primary_doc}"
            )
            return {
                "cik": cik,
                "ticker": ticker.upper(),
                "company_name": sub.get("name"),
                "accession": accession,
                "filing_date": filing_date,
                "primary_document": primary_doc,
                "document_url": doc_url,
                "filing_index_url": (
                    f"https://www.sec.gov/cgi-bin/browse-edgar?"
                    f"action=getcompany&CIK={cik}&type=DEF+14A"
                ),
            }
    raise EdgarError(f"No DEF 14A found for {ticker}")


def fetch_document(url: str) -> str:
    """Download a filing document (HTML/iXBRL) as text."""
    with _client() as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text
