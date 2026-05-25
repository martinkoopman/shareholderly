"""Use Claude to extract ballot + structured statement data from a DEF 14A.

The proxy HTML is cleaned to plain text, then sent to Claude with a
forced-output tool schema. Claude returns a JSON object matching our
internal proxy schema, which the recommender already understands.
"""

from __future__ import annotations

import json
import re
import warnings

from anthropic import Anthropic
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from . import config

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


_SOURCES_SCHEMA = {
    "type": "object",
    "description": (
        "Map of field_name → 5-25 word LETTER-FOR-LETTER quote from the input "
        "text. RULES: (a) Copy verbatim — no paraphrase, keep footnote markers, "
        "smart quotes, dashes, and special characters intact. "
        "(b) Single paragraph / table cell — no line breaks, no spans across "
        "paragraphs. "
        "(c) Must be UNIQUE in the document — extend a generic phrase with an "
        "adjacent name, year, or number from the SAME paragraph until it's "
        "unique. (d) Aggregate disclosures (e.g. 'each director attended at "
        "least 75%') are legitimate sources — use the same aggregate quote for "
        "every entity it covers; uniqueness applies to the proxy text, not how "
        "many entities reference it. (e) Omit any field where you cannot find a "
        "clean quote. A validator drops any quote that does not match — broken "
        "quotes = lost deep-links into the SEC filing."
    ),
    "additionalProperties": {"type": "string"},
}

_CONTEXT_SCHEMA = {
    "type": "string",
    "description": (
        "A 2-5 word LETTER-FOR-LETTER phrase from the input that appears right "
        "before this object's data and uniquely identifies which entity it is "
        "(e.g. the director's name, the audit-fees section heading, the proposal "
        "topic). Used as a prefix anchor in deep-links so the browser scrolls "
        "to the correct instance when the quote appears multiple times in the filing."
    ),
}


_TOOL = {
    "name": "record_proxy_data",
    "description": "Record the structured contents of a DEF 14A proxy statement.",
    "input_schema": {
        "type": "object",
        "required": ["ballot", "statement_data"],
        "properties": {
            "ballot": {
                "type": "array",
                "description": "Every item that shareholders are being asked to vote on, in order.",
                "items": {
                    "type": "object",
                    "required": ["item_id", "type", "title", "board_recommendation"],
                    "properties": {
                        "item_id": {"type": "string", "description": "Item label as printed (e.g. '1a', '2'). Use sequential numbers if no label is given."},
                        "type": {
                            "type": "string",
                            "enum": [
                                "director_election",
                                "auditor_ratification",
                                "say_on_pay",
                                "equity_plan",
                                "shareholder_environmental",
                                "shareholder_governance",
                                "other",
                            ],
                        },
                        "title": {"type": "string"},
                        "subject_key": {
                            "type": "string",
                            "description": "For director_election, the director's full name. For shareholder proposals, a short slug like 'climate_lobbying' that keys into statement_data.shareholder_proposals.",
                        },
                        "board_recommendation": {"type": "string", "enum": ["FOR", "AGAINST", "ABSTAIN"]},
                    },
                },
            },
            "statement_data": {
                "type": "object",
                "required": ["directors", "auditor", "executive_compensation", "shareholder_proposals"],
                "properties": {
                    "directors": {
                        "type": "object",
                        "description": "Map of director full name → details extracted from director-bio / governance sections.",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "independent": {"type": "boolean"},
                                "tenure_years": {"type": "integer"},
                                "attendance_pct": {"type": "string", "description": "Board-meeting attendance for this director, as a percentage string. If a specific per-director figure is disclosed, return like '95%'. If only an aggregate threshold is disclosed (e.g. 'each director attended at least 75% of meetings'), return '≥75%' to indicate the minimum confirmed value — do NOT fabricate a higher figure. Omit the field entirely if no attendance info is disclosed."},
                                "other_public_boards": {"type": "array", "items": {"type": "string"}},
                                "committees": {"type": "array", "items": {"type": "string"}, "description": "e.g. ['Audit', 'Compensation', 'Nominating']"},
                                "_context": _CONTEXT_SCHEMA,
                                "_sources": _SOURCES_SCHEMA,
                            },
                        },
                    },
                    "auditor": {
                        "type": "object",
                        "properties": {
                            "firm": {"type": "string"},
                            "tenure_years": {"type": "integer"},
                            "audit_fees_usd": {"type": "integer"},
                            "non_audit_fees_usd": {"type": "integer", "description": "Sum of audit-related, tax, and all-other fees."},
                            "_sources": _SOURCES_SCHEMA,
                        },
                    },
                    "executive_compensation": {
                        "type": "object",
                        "properties": {
                            "ceo_pay_usd": {"type": "integer", "description": "CEO total comp for most recent fiscal year from the Summary Comp Table."},
                            "ceo_pay_ratio": {"type": "integer", "description": "CEO-to-median-employee pay ratio (Item 402(u))."},
                            "pay_for_performance_aligned": {"type": "boolean", "description": "Your judgment based on the Pay-vs-Performance disclosure: are CAP and TSR trending together over the disclosed years?"},
                            "_sources": _SOURCES_SCHEMA,
                        },
                    },
                    "equity_plan": {
                        "type": "object",
                        "description": "Only populate if there is an equity-plan ballot item.",
                        "properties": {
                            "expected_dilution_pct": {"type": "number"},
                            "three_year_avg_burn_rate_pct": {"type": "number"},
                            "_sources": _SOURCES_SCHEMA,
                        },
                    },
                    "shareholder_proposals": {
                        "type": "object",
                        "description": "Map of slug → details. Slugs must match subject_key on the corresponding ballot item.",
                        "additionalProperties": {
                            "type": "object",
                            "properties": {
                                "topic": {"type": "string", "description": "One of: 'climate-risk disclosure', 'human-rights impact assessment', 'workforce diversity reporting', 'independent board chair', 'eliminate supermajority', 'special meeting threshold', 'classified board', or a short free-form description if no match."},
                                "proponent": {"type": "string"},
                                "summary": {"type": "string"},
                                "board_position": {"type": "string", "enum": ["FOR", "AGAINST"]},
                                "_context": _CONTEXT_SCHEMA,
                                "_sources": _SOURCES_SCHEMA,
                            },
                        },
                    },
                },
            },
        },
    },
}


_SYSTEM = """You extract structured voting data from a SEC DEF 14A (proxy statement) filing.

Call the record_proxy_data tool exactly ONCE. Follow the tool schema STRICTLY:
- `ballot` MUST be a JSON array of objects (NOT a stringified JSON, NOT a single string). Each director election is a separate item; ratification, say-on-pay, equity plans, and every shareholder proposal are separate items.
- `statement_data` MUST be a JSON object containing `directors`, `auditor`, `executive_compensation`, and `shareholder_proposals`. Fill each one with the entities you find — `directors` is a map of name → object, `shareholder_proposals` is a map of slug → object.
- Omit any individual field you cannot determine from the proxy. Never fabricate values.

For each leaf object you fill (each director, the auditor, executive_compensation, each shareholder proposal), include:
- `_context`: a short verbatim anchor phrase that appears near this entity's data (e.g. the director's name).
- `_sources`: a map of field_name → 5-25 word verbatim quote supporting that field's value. The per-field schema descriptions below explain the conventions for quotes and aggregate disclosures.
"""


def _clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    # Collapse whitespace runs but keep paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Punctuation/whitespace normalisation table — keeps quotes that differ only
# in smart-vs-straight quotes, dash variants, or non-breaking spaces.
_NORMALISE_TRANS = str.maketrans({
    "‘": "'", "’": "'",            # curly single quotes
    "“": '"', "”": '"',            # curly double quotes
    "–": "-", "—": "-", "−": "-",  # en/em/minus dash
    " ": " ", " ": " ", " ": " ",  # non-breaking + thin spaces
})


def _normalise(s: str) -> str:
    """Lower-case, collapse whitespace, fold curly punctuation to ASCII."""
    s = s.translate(_NORMALISE_TRANS)
    return re.sub(r"\s+", " ", s).lower().strip()


def _validate_sources(extracted: dict, text: str) -> dict:
    """Walk extracted; drop _context strings and _sources quotes that wouldn't
    produce a working deep-link.

    A quote is kept iff it:
      1. Is a non-empty string
      2. Contains no line breaks (text-fragment spec can't cross block boundaries)
      3. Appears in the source text (after whitespace + smart-quote normalisation)
      4. Appears EXACTLY ONCE — non-unique quotes would scroll to the wrong instance

    Returns a stats dict broken down by drop reason for diagnostics.
    """
    norm_text = _normalise(text)
    stats = {
        "kept": 0,
        "dropped_empty": 0,
        "dropped_multiline": 0,
        "dropped_not_found": 0,
        "dropped_ambiguous": 0,
        "contexts_kept": 0,
        "contexts_dropped": 0,
    }

    def walk(node):
        if isinstance(node, dict):
            ctx = node.get("_context")
            if isinstance(ctx, str):
                if _normalise(ctx) in norm_text:
                    stats["contexts_kept"] += 1
                else:
                    node.pop("_context")
                    stats["contexts_dropped"] += 1

            srcs = node.get("_sources")
            if isinstance(srcs, dict):
                cleaned: dict[str, str] = {}
                for k, q in srcs.items():
                    if not isinstance(q, str) or not q.strip():
                        stats["dropped_empty"] += 1
                        continue
                    if "\n" in q:
                        stats["dropped_multiline"] += 1
                        continue
                    nq = _normalise(q)
                    occurrences = norm_text.count(nq)
                    if occurrences == 0:
                        stats["dropped_not_found"] += 1
                    elif occurrences > 1:
                        stats["dropped_ambiguous"] += 1
                    else:
                        cleaned[k] = q.strip()
                        stats["kept"] += 1
                node["_sources"] = cleaned

            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(extracted)
    return stats


def extract(html: str, xbrl_facts: dict | None = None) -> dict:
    """Run Claude on the proxy HTML and return the structured dict."""
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in backend/.env")

    text = _clean_html(html)
    facts_hint = (
        f"\n\nXBRL ground-truth facts (use verbatim where applicable): {json.dumps(xbrl_facts)}\n"
        if xbrl_facts
        else ""
    )

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=config.EXTRACTION_MODEL,
        max_tokens=32000,
        system=[
            {
                "type": "text",
                "text": _SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "record_proxy_data"},
        messages=[
            {
                "role": "user",
                "content": f"Proxy statement text follows.{facts_hint}\n\n---\n\n{text}",
            }
        ],
    )

    usage = getattr(resp, "usage", None)
    if usage:
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
        print(
            f"[llm_extractor] usage: input={usage.input_tokens} "
            f"cache_read={cache_read} cache_create={cache_create} "
            f"output={usage.output_tokens} stop_reason={resp.stop_reason}"
        )
    if resp.stop_reason == "max_tokens":
        print(f"[llm_extractor] WARNING: response truncated at max_tokens — output may be incomplete")
    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_proxy_data":
            extracted = dict(block.input)
            stats = _validate_sources(extracted, text)
            print(
                f"[llm_extractor] stop_reason={resp.stop_reason} "
                f"sources kept={stats['kept']} "
                f"dropped: not_found={stats['dropped_not_found']} "
                f"multiline={stats['dropped_multiline']} "
                f"ambiguous={stats['dropped_ambiguous']} "
                f"empty={stats['dropped_empty']} | "
                f"contexts kept={stats['contexts_kept']}/dropped={stats['contexts_dropped']}"
            )
            return extracted
    raise RuntimeError("Claude did not return tool input")
