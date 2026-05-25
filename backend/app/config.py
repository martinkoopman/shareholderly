"""Centralised config and secrets, loaded from .env at import time."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Sonnet 4.6 — strong reasoning, large context, much cheaper than Opus.
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "claude-sonnet-4-6")
