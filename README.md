# Proxy Voter

A small web app that recommends how a fund should vote each line of a
company's proxy ballot, based on the firm's written voting policy.

```
holdings DB ──► proxy ballot + statement ──► voting policy rules ──► recommendation
```

## What's inside

```
goal/
├── backend/                       Python — the brain
│   ├── app/
│   │   ├── main.py                FastAPI web API (HTTP endpoints)
│   │   ├── database.py            reads holdings from SQLite
│   │   ├── proxy_finder.py        loads ballot + statement for a ticker
│   │   ├── policy.py              loads the firm's policy markdown
│   │   └── recommender.py         applies the rules → FOR/AGAINST/ABSTAIN
│   ├── data/holdings.db           sample SQLite DB (created by seed_db.py)
│   ├── sample_proxies/*.json      canned ballot + statement per company
│   ├── policy.md                  the firm's voting policy (human-readable)
│   ├── requirements.txt
│   └── seed_db.py
├── frontend/                      React — the face
│   └── src/
│       ├── App.jsx                top-level UI
│       ├── api.js                 calls the backend
│       └── components/            HoldingsTable, BallotReview, PolicyDrawer
└── run.sh                         one command to start everything
```

## Run it

```
./run.sh
```

The first run installs dependencies (Python venv + npm packages) and seeds
the database — takes ~30 seconds. Subsequent runs start instantly.

Then open the URL Vite prints (usually <http://localhost:5173>, or 5174 if
5173 is busy).

To stop: press Ctrl-C in the terminal where `./run.sh` is running.

## How it works

1. **Holdings come from a database.** `seed_db.py` populates a SQLite file
   at `backend/data/holdings.db` with two sample funds and their positions.
   In production this would be your fund's real positions database.

2. **Proxies come from per-ticker JSON files** in `backend/sample_proxies/`.
   Each file has two parts:
   - `ballot`: the list of items being voted on (the **proxy ballot card**).
   - `statement_data`: the data points pulled from the **proxy statement**
     (director bios, exec comp, auditor fees, shareholder-proposal text…).

   To handle real companies, replace `app/proxy_finder.py` with a fetcher
   that scrapes EDGAR DEF 14A filings or the company IR page.

3. **The voting policy lives in `policy.md`.** The same rules are encoded
   as Python in `app/recommender.py` — one handler per proposal type.
   Edit both together when you change a rule.

4. **The recommender** matches each ballot item to its policy rules,
   pulls the relevant evidence from the proxy statement, and returns a
   vote + a one-line rationale.

5. **The UI** shows fund holdings, lets you drill into any company's
   ballot, and highlights items where our vote disagrees with the
   board's recommendation.

## Extending it

| To do this…                              | Edit this file                              |
|------------------------------------------|---------------------------------------------|
| Add another fund or holdings             | `backend/seed_db.py` (then re-run it)       |
| Add a new company's proxy                | drop a new `TICKER.json` in `sample_proxies/`|
| Change a voting rule                     | `policy.md` AND `app/recommender.py`        |
| Support a new proposal type              | add a handler in `app/recommender.py`       |
| Fetch real proxies from EDGAR            | replace `app/proxy_finder.py`               |
| Change the look of the UI                | `frontend/src/styles.css`                   |
