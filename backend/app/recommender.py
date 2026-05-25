"""Generate a vote recommendation for each item on a proxy ballot.

For each ballot item:
  1. Pull the relevant data points from the proxy statement.
  2. Apply the policy rules for that proposal type, in order.
  3. The first rule that fires wins; otherwise vote with the default.
"""

from dataclasses import dataclass, field


@dataclass
class Recommendation:
    item_id: str
    title: str
    type: str
    board_recommendation: str
    vote: str                          # "FOR" | "AGAINST" | "ABSTAIN"
    rationale: str
    evidence: dict                     # the data points pulled from the statement
    evidence_sources: dict = field(default_factory=dict)  # field_name → verbatim quote
    evidence_context: str = ""         # prefix anchor for deep-links


def recommend_ballot(proxy: dict) -> list[Recommendation]:
    statement = proxy["statement_data"]
    return [_recommend_item(item, statement) for item in proxy["ballot"]]


def _recommend_item(item: dict, statement: dict) -> Recommendation:
    handler = _HANDLERS.get(item["type"], _default_handler)
    vote, rationale, evidence, sources, context = handler(item, statement)
    return Recommendation(
        item_id=item["item_id"],
        title=item["title"],
        type=item["type"],
        board_recommendation=item.get("board_recommendation", "FOR"),
        vote=vote,
        rationale=rationale,
        evidence=evidence,
        evidence_sources=sources,
        evidence_context=context,
    )


def _split(d: dict | None) -> tuple[dict, dict, str]:
    """Return (data_without_meta, sources_dict, context_string)."""
    d = d or {}
    sources = d.get("_sources", {}) or {}
    context = d.get("_context", "") or ""
    data = {k: v for k, v in d.items() if not k.startswith("_")}
    return data, sources, context


# --- per-proposal-type handlers ------------------------------------------------

def _nz(value, default):
    """Coalesce None or missing → default. Differs from dict.get which only handles missing."""
    return default if value is None else value


def _parse_pct(value) -> float | None:
    """Parse a percentage-ish field that may be an int, a plain string, or a
    threshold string like '≥75%'. Returns the numeric floor, or None if
    nothing usable. For '≥X%' returns X — the minimum confirmed value.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace("%", "").replace("≥", "").replace(">=", "").strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _director_election(item, statement):
    name = item["subject_key"]
    raw = statement.get("directors", {}).get(name, {})
    data, sources, context = _split(raw)
    if not context:
        context = name  # director's name is a perfect natural anchor
    evidence = {"director": name, **data}

    attendance_raw = data.get("attendance_pct")
    attendance = _parse_pct(attendance_raw)
    independent = _nz(data.get("independent"), True)
    committees = _nz(data.get("committees"), []) or []
    other_boards = _nz(data.get("other_public_boards"), []) or []
    tenure = _nz(data.get("tenure_years"), 0)

    # Only fail the rule if attendance was disclosed AND is below threshold.
    # An aggregate disclosure like "≥75%" parses to 75 (the floor) and passes.
    if attendance is not None and attendance < 75:
        return "AGAINST", f"Attendance {attendance_raw} is below Vanguard's 75% threshold.", evidence, sources, context
    if not independent and any(c in {"Audit", "Compensation", "Nominating", "Nominating/Governance", "Governance"} for c in committees):
        return "AGAINST", f"Non-independent director sits on a key committee ({committees}); Vanguard expects audit, compensation, and nominating/governance committees to be entirely independent.", evidence, sources, context
    if len(other_boards) > 4:
        return "AGAINST", f"Overboarded: serves on {len(other_boards)} public-company boards; Vanguard's threshold is 4.", evidence, sources, context
    # Tenure-based AGAINST rule intentionally omitted — Vanguard does not cap director tenure.
    _ = tenure  # field still surfaced as evidence
    return "FOR", "Meets Vanguard's independence, attendance, and director-capacity criteria.", evidence, sources, context


def _auditor_ratification(item, statement):
    data, sources, context = _split(statement.get("auditor"))
    evidence = data
    audit_fees = _nz(data.get("audit_fees_usd"), 0)
    non_audit_fees = _nz(data.get("non_audit_fees_usd"), 0)
    # Vanguard: AGAINST when non-audit fees exceed audit fees (absent a clear
    # disclosure that the non-audit work does not impair independence). No fixed
    # tenure cap.
    ratio = non_audit_fees / max(audit_fees, 1)
    if ratio > 1.0:
        return "AGAINST", f"Non-audit fees ({ratio:.0%} of audit fees) exceed audit fees; Vanguard flags this as an independence concern.", evidence, sources, context
    return "FOR", "Non-audit fees are within Vanguard's auditor-independence threshold.", evidence, sources, context


def _say_on_pay(item, statement):
    data, sources, context = _split(statement.get("executive_compensation"))
    evidence = data
    aligned = _nz(data.get("pay_for_performance_aligned"), True)
    # Vanguard evaluates Say-on-Pay case-by-case; the only automatable trigger
    # we encode is the pay-for-performance alignment signal. No CEO-pay-ratio
    # threshold (Vanguard does not use one).
    if not aligned:
        return "AGAINST", "Pay-for-performance is not aligned over the trailing 3-year period (Vanguard's primary Say-on-Pay concern).", evidence, sources, context
    return "FOR", "Pay-for-performance appears aligned; no Vanguard red flags detected.", evidence, sources, context


def _equity_plan(item, statement):
    data, sources, context = _split(statement.get("equity_plan"))
    evidence = data
    dilution = _nz(data.get("expected_dilution_pct"), 0)
    burn = _nz(data.get("three_year_avg_burn_rate_pct"), 0)
    if dilution > 20:
        return "AGAINST", f"Total potential dilution of {dilution}% exceeds Vanguard's 20% threshold.", evidence, sources, context
    if burn > 4:
        return "AGAINST", f"3-year avg annual grant rate of {burn}% exceeds Vanguard's 4% threshold.", evidence, sources, context
    return "FOR", "Dilution and grant rate within Vanguard's thresholds.", evidence, sources, context


_E_AND_S_FOR_TOPICS = {
    "climate-risk disclosure",
    "human-rights impact assessment",
    "workforce diversity reporting",
}


def _shareholder_environmental(item, statement):
    raw = statement.get("shareholder_proposals", {}).get(item.get("subject_key"), {})
    data, sources, context = _split(raw)
    evidence = data
    if data.get("topic") in _E_AND_S_FOR_TOPICS:
        return "FOR", f"Policy supports proposals on {data['topic']}.", evidence, sources, context
    return "ABSTAIN", "Proposal does not match a supported E&S category; flag for manual review.", evidence, sources, context


_GOV_FOR_TOPICS = {
    "eliminate supermajority",
    "special meeting threshold",
}
# Vanguard generally votes AGAINST shareholder proposals to require an
# independent board chair, viewing leadership structure as the board's purview
# absent significant concerns about board independence/effectiveness.
_GOV_AGAINST_TOPICS = {
    "classified board",
    "independent board chair",
}


def _shareholder_governance(item, statement):
    raw = statement.get("shareholder_proposals", {}).get(item.get("subject_key"), {})
    data, sources, context = _split(raw)
    evidence = data
    topic = data.get("topic", "")
    if topic in _GOV_FOR_TOPICS:
        return "FOR", f"Policy supports proposals on {topic}.", evidence, sources, context
    if topic in _GOV_AGAINST_TOPICS:
        return "AGAINST", f"Policy opposes proposals on {topic}.", evidence, sources, context
    return "ABSTAIN", "Governance proposal does not match a coded rule; flag for manual review.", evidence, sources, context


def _default_handler(item, statement):
    return "ABSTAIN", "Proposal type not covered by policy; flag for manual review.", {}, {}, ""


_HANDLERS = {
    "director_election":         _director_election,
    "auditor_ratification":      _auditor_ratification,
    "say_on_pay":                _say_on_pay,
    "equity_plan":               _equity_plan,
    "shareholder_environmental": _shareholder_environmental,
    "shareholder_governance":    _shareholder_governance,
}
