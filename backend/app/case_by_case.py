"""Case-by-case AI analysis for ballot items the coded rules can't decide.

When a proposal's topic or type doesn't match any policy rule, send the
proposal text to Claude along with the firm's policy markdown and ask for
a vote grounded in the policy's narrative principles. Returns a vote and
a short rationale; never raises on bad model output (callers fall back to
the original ABSTAIN).
"""

from __future__ import annotations

from anthropic import Anthropic

from . import config


_TOOL = {
    "name": "record_vote",
    "description": "Record a vote and rationale for a proxy ballot item analyzed against the firm's voting policy.",
    "input_schema": {
        "type": "object",
        "required": ["vote", "rationale"],
        "properties": {
            "vote": {
                "type": "string",
                "enum": ["FOR", "AGAINST", "ABSTAIN"],
                "description": "How the firm should vote. Use ABSTAIN only when the policy is genuinely silent or self-contradictory on this kind of proposal.",
            },
            "rationale": {
                "type": "string",
                "description": (
                    "2-4 sentences grounded in the policy. Quote a short phrase "
                    "from the policy where you can. Be specific about which aspect "
                    "of the proposal triggers which policy stance."
                ),
            },
        },
    },
}


_SYSTEM = """You apply a firm's proxy voting policy to a specific ballot item.

You receive: (1) the firm's full policy, (2) one ballot item that the firm's *coded* rules could not decide. Call the record_vote tool exactly ONCE.

- The policy is the only source of truth. Do not invent rules or apply outside knowledge of governance "best practices."
- ABSTAIN is correct only when the policy is genuinely silent. If the policy uses "case-by-case" or "evaluated on its merits" language for this kind of proposal, use the surrounding principles to make a defensible call — do NOT default to ABSTAIN just because no explicit rule fires.
- Quote the specific policy phrase that drives your verdict in the rationale.
"""


def analyze_proposal(
    ballot_item: dict,
    proposal_data: dict,
    policy_markdown: str,
) -> dict:
    """Return ``{"vote": "FOR"|"AGAINST"|"ABSTAIN", "rationale": "..."}``."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    # Prefer the verbatim full text from the proxy when we extracted it
    # (extraction field `full_text` captures the proposal + supporting
    # statement + board response). Fall back to the short summary if the
    # cache is from an older extraction pass.
    full_text = (proposal_data.get("full_text") or "").strip()
    body_block = (
        f"Proposal text (verbatim from proxy):\n{full_text}"
        if full_text
        else f"Summary (LLM-paraphrased): {proposal_data.get('summary', '(none)')}"
    )

    user_msg = (
        "--- FIRM POLICY ---\n"
        f"{policy_markdown}\n\n"
        "--- BALLOT ITEM ---\n"
        f"Title: {ballot_item.get('title', '(no title)')}\n"
        f"Type:  {ballot_item.get('type', '(unknown)')}\n"
        f"Board recommends: {ballot_item.get('board_recommendation', '(unstated)')}\n"
        f"Topic (classified): {proposal_data.get('topic', '(unclassified)')}\n"
        f"Proponent: {proposal_data.get('proponent', '(unstated)')}\n\n"
        f"{body_block}\n"
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.EXTRACTION_MODEL,
        max_tokens=800,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_vote"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_vote":
            out = dict(block.input)
            if out.get("vote") in ("FOR", "AGAINST", "ABSTAIN") and out.get("rationale"):
                return out
            raise RuntimeError(f"Claude returned malformed vote: {out}")
    raise RuntimeError("Claude did not return tool input")
