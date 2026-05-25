"""FastAPI entrypoint.

Run with:   uvicorn app.main:app --reload --port 8000
"""

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import database, policy, proxy_finder, recommender

app = FastAPI(title="Shareholderly API", version="0.1.0")

# Allow the React dev server to call this API.
# Vite picks port 5173 by default; if that's busy it tries 5174, 5175, ...
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/funds")
def get_funds():
    return database.list_funds()


@app.get("/api/funds/{fund_id}/holdings")
def get_holdings(fund_id: str):
    holdings = database.list_holdings(fund_id)
    if not holdings:
        raise HTTPException(status_code=404, detail=f"No holdings for fund {fund_id}")
    enriched = []
    available = set(proxy_finder.available_tickers())
    for h in holdings:
        enriched.append({**h, "proxy_available": h["ticker"] in available})
    return enriched


@app.get("/api/proxies/{ticker}")
def get_proxy(ticker: str):
    try:
        return proxy_finder.get_proxy(ticker)
    except proxy_finder.ProxyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/proxies/{ticker}/refresh")
def refresh_proxy(ticker: str):
    """Fetch the latest DEF 14A from EDGAR, extract it, cache it."""
    try:
        data = proxy_finder.refresh(ticker)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refresh failed: {e}")
    return {
        "ticker": data["ticker"],
        "source": data["source"],
        "ballot_items": len(data.get("ballot", [])),
    }


@app.get("/api/proxies/{ticker}/recommendations")
def get_recommendations(ticker: str):
    try:
        proxy = proxy_finder.get_proxy(ticker)
    except proxy_finder.ProxyNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    recs = recommender.recommend_ballot(proxy)
    return {
        "ticker": proxy["ticker"],
        "company_name": proxy["company_name"],
        "meeting_date": proxy.get("meeting_date"),
        "proxy_statement_url": proxy["proxy_statement_url"],
        "source": proxy.get("source", {"kind": "fixture"}),
        "recommendations": [asdict(r) for r in recs],
    }


@app.get("/api/policy")
def get_policy():
    return {"markdown": policy.load_policy_markdown()}
