#!/usr/bin/env bash
# Start the proxy-voter app (backend + frontend).
# Usage:  ./run.sh        (Ctrl-C stops both)

set -e
cd "$(dirname "$0")"

# Ensure backend venv exists and DB is seeded.
if [ ! -d backend/.venv ]; then
  echo "First-time setup: creating Python virtual environment..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements.txt
fi
if [ ! -f backend/data/holdings.db ]; then
  echo "Seeding sample database..."
  backend/.venv/bin/python backend/seed_db.py
fi

# Ensure frontend deps exist.
if [ ! -d frontend/node_modules ]; then
  echo "First-time setup: installing frontend packages..."
  (cd frontend && npm install --silent)
fi

# Start backend (port 8000) and frontend (Vite picks 5173+) in parallel.
echo "Starting backend on http://localhost:8000 ..."
(cd backend && .venv/bin/uvicorn app.main:app --port 8000) &
BACKEND_PID=$!

echo "Starting frontend (Vite will print the URL it picked) ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!

# Stop both when this script exits.
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait
