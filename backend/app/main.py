"""FastAPI entrypoint.

Run with:   uvicorn app.main:app --reload --port 8000
"""

from dataclasses import asdict

from fastapi import FastAPI, HTTPException, UploadFile, File

from fastapi.middleware.cors import CORSMiddleware

from . import database, holdings_importer, policy, policy_importer, proxy_finder, recommender

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
    active = policy.load_active_policy()
    return {
        "markdown": policy.load_policy_markdown(),
        "name": active.get("name"),
        "effective": active.get("effective"),
        "rules": active.get("rules", {}),
    }


@app.post("/api/policy/import")
async def import_policy(file: UploadFile = File(...)):
    """Replace the active policy with one extracted from an uploaded PDF."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload must be a .pdf file.")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MB upload cap.")
    try:
        extracted = policy_importer.import_from_pdf(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Policy extraction failed: {e}")

    structured = {
        "name": extracted.get("name", "Imported policy"),
        "effective": extracted.get("effective", ""),
        "source": file.filename,
        "rules": extracted.get("rules", {}),
    }
    markdown = extracted.get("markdown") or f"# {structured['name']}\n\n(No markdown summary returned.)"
    policy.save_active_policy(structured, markdown)
    return {
        "name": structured["name"],
        "effective": structured["effective"],
        "rules": structured["rules"],
        "markdown": markdown,
    }


@app.post("/api/funds/{fund_id}/holdings/import")
async def import_holdings(fund_id: str, file: UploadFile = File(...)):
    """Replace a fund's holdings with rows parsed from an uploaded CSV."""
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload must be a .csv file.")
    csv_bytes = await file.read()
    if len(csv_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV exceeds 5 MB upload cap.")
    try:
        result = holdings_importer.import_csv(fund_id, csv_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result
