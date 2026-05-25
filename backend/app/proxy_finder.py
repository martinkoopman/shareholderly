"""Locate a company's proxy ballot card and proxy statement.

Resolution order:
  1. Disk cache at data/extracted_proxies/<TICKER>.json
  2. sample_proxies/<TICKER>.json (the hand-curated fixtures)

A live refresh (``refresh()``) pulls the latest DEF 14A from EDGAR,
extracts structured data via XBRL + Claude, and writes the cache.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import edgar, llm_extractor, xbrl_extractor

ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "sample_proxies"
CACHE_DIR = ROOT / "data" / "extracted_proxies"


class ProxyNotFoundError(Exception):
    pass


def get_proxy(ticker: str) -> dict:
    """Return cached or fixture proxy data for one ticker."""
    ticker = ticker.upper()
    cached = CACHE_DIR / f"{ticker}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    fixture = FIXTURES_DIR / f"{ticker}.json"
    if fixture.exists():
        data = json.loads(fixture.read_text())
        data.setdefault("source", {"kind": "fixture"})
        return data
    raise ProxyNotFoundError(f"No proxy data for {ticker}")


def available_tickers() -> list[str]:
    out: set[str] = set()
    for p in FIXTURES_DIR.glob("*.json"):
        out.add(p.stem)
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*.json"):
            out.add(p.stem)
    return sorted(out)


def refresh(ticker: str) -> dict:
    """Fetch the latest DEF 14A from EDGAR, extract it, cache, and return."""
    ticker = ticker.upper()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    meta = edgar.latest_def14a(ticker)
    html = edgar.fetch_document(meta["document_url"])
    xbrl_facts = xbrl_extractor.extract_facts(html)
    extracted = llm_extractor.extract(html, xbrl_facts=xbrl_facts)

    # Merge XBRL CEO pay over LLM's value when available — XBRL is authoritative.
    # Defensive: the LLM occasionally returns a non-dict where the schema says
    # an object should be (e.g. flattens executive_compensation to a string).
    # Coerce / repair rather than crashing.
    if "ceo_pay_usd" in xbrl_facts:
        sd = extracted.get("statement_data")
        if not isinstance(sd, dict):
            sd = {}
            extracted["statement_data"] = sd
        ec = sd.get("executive_compensation")
        if not isinstance(ec, dict):
            ec = {}
            sd["executive_compensation"] = ec
        ec["ceo_pay_usd"] = xbrl_facts["ceo_pay_usd"]
        srcs = ec.get("_sources")
        if not isinstance(srcs, dict):
            srcs = {}
            ec["_sources"] = srcs
        srcs["ceo_pay_usd"] = f"{xbrl_facts['ceo_pay_usd']:,}"
        if not isinstance(ec.get("_context"), str):
            ec["_context"] = "Total"

    out = {
        "ticker": ticker,
        "company_name": meta["company_name"],
        "meeting_date": None,  # the meeting date itself is in the proxy text; LLM could pull it
        "proxy_statement_url": meta["document_url"],
        "source": {
            "kind": "edgar",
            "accession": meta["accession"],
            "filing_date": meta["filing_date"],
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "xbrl_facts": xbrl_facts,
        },
        **extracted,
    }

    (CACHE_DIR / f"{ticker}.json").write_text(json.dumps(out, indent=2))
    return out
