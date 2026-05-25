"""Pull machine-tagged facts from a DEF 14A's inline XBRL.

The SEC tags Executive Compensation Disclosure (ECD) data points — most
importantly the Pay-vs-Performance table introduced in 2023. We use these
where available and let the LLM extractor handle everything else.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

# Tag names in the http://xbrl.sec.gov/ecd/ namespace we care about.
# PEO = Principal Executive Officer (the CEO, in practice).
_PEO_TOTAL_COMP_TAGS = {
    "PeoTotalCompAmt",
    "PeoActuallyPaidCompAmt",
}


def extract_facts(html: str) -> dict:
    """Return a dict of XBRL-tagged facts found in the document.

    Currently captures the most recent year's PEO total compensation and
    actually-paid compensation; we use the PEO total as the CEO pay number.
    Returns an empty dict if no XBRL tags are present.
    """
    soup = BeautifulSoup(html, "lxml")
    facts: dict[str, list[dict]] = {}

    # Inline XBRL uses ix:nonfraction for numbers.
    for tag in soup.find_all(["ix:nonfraction", "ix:nonFraction"]):
        name_attr = tag.get("name", "")
        if ":" not in name_attr:
            continue
        prefix, local = name_attr.split(":", 1)
        if prefix != "ecd":
            continue
        try:
            value = float(tag.get_text().replace(",", "").strip() or "0")
            scale = int(tag.get("scale") or "0")
            sign = -1 if tag.get("sign") == "-" else 1
            numeric = sign * value * (10 ** scale)
        except ValueError:
            continue
        facts.setdefault(local, []).append(
            {"value": numeric, "context": tag.get("contextref", "")}
        )

    out: dict = {}
    # Pick the largest PEO total comp value found (typically the most recent year).
    for tag_name in _PEO_TOTAL_COMP_TAGS:
        if tag_name in facts:
            out[tag_name] = max(f["value"] for f in facts[tag_name])

    if "PeoTotalCompAmt" in out:
        out["ceo_pay_usd"] = int(out["PeoTotalCompAmt"])

    return out
