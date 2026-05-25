"""Load the firm's voting policy.

The policy is authored in ``policy.md`` for humans to read and review.
The recommender encodes the same rules as Python (see ``recommender.py``);
this module simply exposes the markdown so the UI can display it.
"""

from pathlib import Path

POLICY_PATH = Path(__file__).parent.parent / "policy.md"


def load_policy_markdown() -> str:
    return POLICY_PATH.read_text(encoding="utf-8")
