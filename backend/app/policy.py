"""Load the active firm voting policy.

The policy lives in two places:
 - ``data/active_policy.json``: a structured rule-set the recommender consumes.
 - ``policy.md``: the long-form human-readable version shown in the UI.

When a user imports a new policy via PDF, both are rewritten.
"""

import json
from pathlib import Path

POLICY_MD_PATH = Path(__file__).parent.parent / "policy.md"
ACTIVE_POLICY_PATH = Path(__file__).parent.parent / "data" / "active_policy.json"


def load_policy_markdown() -> str:
    return POLICY_MD_PATH.read_text(encoding="utf-8")


def load_active_policy() -> dict:
    return json.loads(ACTIVE_POLICY_PATH.read_text(encoding="utf-8"))


def save_active_policy(policy: dict, markdown: str) -> None:
    """Replace both the structured policy and the human-readable markdown."""
    ACTIVE_POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_POLICY_PATH.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    POLICY_MD_PATH.write_text(markdown, encoding="utf-8")
