"""Import a proxy voting policy from a PDF.

Pipeline: PDF bytes → pypdf text extraction → Claude (tool-use forced) →
structured rules dict + a markdown summary. The caller writes both via
``policy.save_active_policy``.

The structured schema mirrors what ``recommender.py`` consumes. The LLM is
asked to leave fields blank when the policy is silent on a topic — better
that votes default to FOR than that we invent thresholds.
"""

from __future__ import annotations

import io
import json

import pypdf
from anthropic import Anthropic

from . import config


_RULES_SCHEMA = {
    "type": "object",
    "description": "Extracted voting thresholds. Omit any field the policy does not specify.",
    "properties": {
        "director_election": {
            "type": "object",
            "properties": {
                "attendance_pct_min": {"type": "number", "description": "Minimum board/committee meeting attendance percentage; vote AGAINST any director below this."},
                "max_other_public_boards": {"type": "integer", "description": "Vote AGAINST any director on more than this many other public-company boards."},
                "max_tenure_years": {"type": "integer", "description": "Vote AGAINST any director with tenure exceeding this. Omit if the policy does not cap tenure."},
                "non_indep_disqualifying_committees": {"type": "array", "items": {"type": "string"}, "description": "Committees on which a non-independent director triggers AGAINST (e.g. 'Audit', 'Compensation', 'Nominating', 'Nominating/Governance', 'Governance')."}
            }
        },
        "auditor_ratification": {
            "type": "object",
            "properties": {
                "max_non_audit_to_audit_ratio": {"type": "number", "description": "Vote AGAINST when non-audit fees / audit fees exceeds this. e.g. 1.0 means 'when non-audit > audit'; 0.5 means 'when non-audit > 50% of audit'."},
                "max_tenure_years": {"type": "integer", "description": "Vote AGAINST when auditor tenure exceeds this. Omit if not specified."}
            }
        },
        "say_on_pay": {
            "type": "object",
            "properties": {
                "require_pay_for_performance_aligned": {"type": "boolean", "description": "If true, vote AGAINST when pay-for-performance is not aligned over the trailing period."},
                "max_ceo_pay_ratio": {"type": "integer", "description": "Vote AGAINST when CEO-to-median pay ratio exceeds this. Omit if the policy does not use this metric."}
            }
        },
        "equity_plan": {
            "type": "object",
            "properties": {
                "max_dilution_pct": {"type": "number", "description": "Vote AGAINST if total potential dilution exceeds this percentage."},
                "max_burn_rate_pct": {"type": "number", "description": "Vote AGAINST if 3-year average burn / annual grant rate exceeds this percentage."}
            }
        },
        "shareholder_environmental": {
            "type": "object",
            "properties": {
                "for_topics": {"type": "array", "items": {"type": "string"}, "description": "E&S topics the policy explicitly SUPPORTS. Use these exact slugs where applicable: 'climate-risk disclosure', 'human-rights impact assessment', 'workforce diversity reporting'. Add other slugs when the policy supports something else."}
            }
        },
        "shareholder_governance": {
            "type": "object",
            "properties": {
                "for_topics": {"type": "array", "items": {"type": "string"}, "description": "Governance topics the policy SUPPORTS. Common slugs: 'eliminate supermajority', 'special meeting threshold', 'independent board chair', 'majority voting'."},
                "against_topics": {"type": "array", "items": {"type": "string"}, "description": "Governance topics the policy OPPOSES. Common slugs: 'classified board', 'independent board chair' (Vanguard opposes this), 'cumulative voting'."}
            }
        }
    }
}


_TOOL = {
    "name": "record_policy",
    "description": "Record the structured contents of a proxy voting policy document.",
    "input_schema": {
        "type": "object",
        "required": ["name", "rules", "markdown"],
        "properties": {
            "name": {"type": "string", "description": "Official policy name + issuing entity (e.g. 'Vanguard — Proxy Voting Policy for U.S. Portfolio Companies')."},
            "effective": {"type": "string", "description": "Effective date or version label as printed in the document (e.g. 'January 2026'). Empty if unstated."},
            "rules": _RULES_SCHEMA,
            "markdown": {"type": "string", "description": "A clean, human-readable markdown summary of the policy organised by proposal type. Section headers should map to: Director Elections, Auditor Ratification, Say-on-Pay, Equity Plans, Shareholder Proposals — Environmental & Social, Shareholder Proposals — Governance. Use bullet points for each rule. Cite verbatim thresholds where possible. Aim for 50–120 lines."}
        }
    }
}


_SYSTEM = """You extract structured voting rules from a proxy voting policy document.

Call the record_policy tool exactly ONCE.

Rules:
- Omit any threshold the policy does not explicitly specify. Do NOT invent values. It is better to leave a field blank (so the recommender defaults to vote FOR) than to fabricate a number.
- For topic lists, only include topics the policy explicitly addresses; if unsure, omit.
- For percentages, return the number itself (e.g. 75 for 75%, 1.0 for 100%).
- The markdown summary should faithfully reflect what is in the document, including notes about case-by-case evaluation, exceptions, and anything the policy leaves to discretion.
"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for i, page in enumerate(reader.pages):
        parts.append(f"\n\n========= PAGE {i+1} =========\n")
        parts.append(page.extract_text() or "")
    return "".join(parts).strip()


def import_from_pdf(pdf_bytes: bytes) -> dict:
    """Return {name, effective, rules, markdown} extracted from the PDF."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in backend/.env")

    text = extract_text_from_pdf(pdf_bytes)
    if not text or len(text) < 200:
        raise ValueError("Could not extract usable text from the PDF (got <200 chars).")

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.EXTRACTION_MODEL,
        max_tokens=16000,
        system=_SYSTEM,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_policy"},
        messages=[{"role": "user", "content": f"Policy text follows.\n\n---\n\n{text}"}],
    )

    usage = getattr(resp, "usage", None)
    if usage:
        print(f"[policy_importer] usage: input={usage.input_tokens} output={usage.output_tokens} stop_reason={resp.stop_reason}")

    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_policy":
            return dict(block.input)
    raise RuntimeError("Claude did not return tool input")
