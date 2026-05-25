"""Generate a vote recommendation for each item on a proxy ballot.

The recommender is parameterised by the *active policy* loaded from
``data/active_policy.json``. Each per-proposal handler reads its thresholds
from that policy at call time, so swapping policies (e.g. via PDF import)
changes the votes without code changes.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import case_by_case, policy as policy_loader


# Marker substrings used in handler rationales to identify ABSTAINs that come
# from a coded-rule miss (vs. a legitimate "policy is silent" ABSTAIN). The
# orchestrator uses this to decide whether to retry via AI analysis.
_UNMATCHED_MARKERS = ("does not match a coded", "not covered by")


@dataclass
class Recommendation:
    item_id: str
    title: str
    type: str
    board_recommendation: str
    vote: str                          # "FOR" | "AGAINST" | "ABSTAIN"
    rationale: str
    evidence: dict
    evidence_sources: dict = field(default_factory=dict)
    evidence_context: str = ""
    ai_assisted: bool = False          # true when the case-by-case LLM decided


def recommend_ballot(
    proxy: dict,
    policy: dict | None = None,
    *,
    enable_ai_fallback: bool = True,
) -> list[Recommendation]:
    """Apply the active (or passed-in) policy to every ballot item.

    For items that the coded rules cannot decide (an "unmatched" ABSTAIN),
    optionally run a case-by-case LLM analysis against the policy markdown.
    """
    if policy is None:
        policy = policy_loader.load_active_policy()
    rules = policy.get("rules", {})
    policy_name = policy.get("name", "the active policy")
    statement = proxy["statement_data"]

    # First pass: run all the cheap coded rules.
    recs: list[Recommendation] = []
    pending_ai: list[tuple[int, dict]] = []  # (index in recs, ballot item)
    for idx, item in enumerate(proxy["ballot"]):
        rec = _recommend_item(item, statement, rules, policy_name)
        if enable_ai_fallback and _is_unmatched_abstain(rec):
            pending_ai.append((idx, item))
        recs.append(rec)

    # Second pass: run all the AI fallbacks in parallel — each one is a
    # network-bound LLM call, so sequential is wall-time death for ballots
    # with many novel proposals (e.g. MSFT with 4 case-by-case items hits
    # ~30s sequentially vs ~8s parallel).
    if pending_ai:
        policy_md = policy_loader.load_policy_markdown()

        def _run_one(idx: int, item: dict) -> tuple[int, dict | Exception]:
            try:
                proposal_data = _lookup_proposal_data(item, statement)
                return idx, case_by_case.analyze_proposal(item, proposal_data, policy_md)
            except Exception as e:  # noqa: BLE001 — keep ballot alive on any failure
                return idx, e

        # Anthropic's HTTP client tolerates concurrent requests; cap workers
        # to keep us under the per-minute token rate limit on smaller tiers.
        with ThreadPoolExecutor(max_workers=min(len(pending_ai), 6)) as pool:
            for idx, result in pool.map(lambda args: _run_one(*args), pending_ai):
                if isinstance(result, Exception):
                    recs[idx].rationale += f" (AI fallback unavailable: {result})"
                else:
                    recs[idx].vote = result["vote"]
                    recs[idx].rationale = result["rationale"]
                    recs[idx].ai_assisted = True

    return recs


def _is_unmatched_abstain(rec: Recommendation) -> bool:
    return rec.vote == "ABSTAIN" and any(m in rec.rationale for m in _UNMATCHED_MARKERS)


def _lookup_proposal_data(item: dict, statement: dict) -> dict:
    """Pull the structured proposal block, if any, for a ballot item."""
    if item.get("type") in ("shareholder_environmental", "shareholder_governance"):
        return statement.get("shareholder_proposals", {}).get(item.get("subject_key"), {})
    return {}


def _recommend_item(item: dict, statement: dict, rules: dict, policy_name: str) -> Recommendation:
    handler = _HANDLERS.get(item["type"], _default_handler)
    vote, rationale, evidence, sources, context = handler(item, statement, rules, policy_name)
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


def _nz(value, default):
    """Coalesce None or missing → default."""
    return default if value is None else value


def _parse_pct(value) -> float | None:
    """Parse a percentage that may be int, float, or threshold string like '≥75%'."""
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


# --- per-proposal-type handlers ----------------------------------------------

def _director_election(item, statement, rules, policy_name):
    cfg = rules.get("director_election", {})
    name = item["subject_key"]
    raw = statement.get("directors", {}).get(name, {})
    data, sources, context = _split(raw)
    if not context:
        context = name
    evidence = {"director": name, **data}

    attendance = _parse_pct(data.get("attendance_pct"))
    independent = _nz(data.get("independent"), True)
    committees = _nz(data.get("committees"), []) or []
    other_boards = _nz(data.get("other_public_boards"), []) or []
    tenure = _parse_pct(data.get("tenure_years"))

    attendance_min = cfg.get("attendance_pct_min")
    if attendance_min is not None and attendance is not None and attendance < attendance_min:
        return "AGAINST", f"Attendance {data.get('attendance_pct')} is below the {attendance_min}% threshold set by {policy_name}.", evidence, sources, context

    disq_committees = set(cfg.get("non_indep_disqualifying_committees", []))
    if disq_committees and not independent and any(c in disq_committees for c in committees):
        return "AGAINST", f"Non-independent director sits on a key committee ({committees}); {policy_name} requires these to be independent.", evidence, sources, context

    max_boards = cfg.get("max_other_public_boards")
    if max_boards is not None and len(other_boards) > max_boards:
        return "AGAINST", f"Overboarded: serves on {len(other_boards)} public-company boards; {policy_name} threshold is {max_boards}.", evidence, sources, context

    max_tenure = cfg.get("max_tenure_years")
    if max_tenure is not None and tenure is not None and tenure > max_tenure:
        return "AGAINST", f"Tenure of {int(tenure)} years exceeds the {max_tenure}-year threshold set by {policy_name}.", evidence, sources, context

    return "FOR", f"Meets all director criteria under {policy_name}.", evidence, sources, context


def _auditor_ratification(item, statement, rules, policy_name):
    cfg = rules.get("auditor_ratification", {})
    data, sources, context = _split(statement.get("auditor"))
    evidence = data

    max_tenure = cfg.get("max_tenure_years")
    tenure = _nz(data.get("tenure_years"), 0)
    if max_tenure is not None and tenure > max_tenure:
        return "AGAINST", f"Auditor tenure of {tenure} years exceeds the {max_tenure}-year threshold set by {policy_name}.", evidence, sources, context

    max_ratio = cfg.get("max_non_audit_to_audit_ratio")
    if max_ratio is not None:
        audit_fees = _nz(data.get("audit_fees_usd"), 0)
        non_audit_fees = _nz(data.get("non_audit_fees_usd"), 0)
        ratio = non_audit_fees / max(audit_fees, 1)
        if ratio > max_ratio:
            return "AGAINST", f"Non-audit fees ({ratio:.0%} of audit fees) exceed the {max_ratio:.0%} threshold set by {policy_name}.", evidence, sources, context

    return "FOR", f"Auditor independence within thresholds set by {policy_name}.", evidence, sources, context


def _say_on_pay(item, statement, rules, policy_name):
    cfg = rules.get("say_on_pay", {})
    data, sources, context = _split(statement.get("executive_compensation"))
    evidence = data

    max_ratio = cfg.get("max_ceo_pay_ratio")
    if max_ratio is not None:
        ratio = _nz(data.get("ceo_pay_ratio"), 0)
        if ratio > max_ratio:
            return "AGAINST", f"CEO pay ratio of {ratio}x exceeds the {max_ratio}x threshold set by {policy_name}.", evidence, sources, context

    if cfg.get("require_pay_for_performance_aligned", False):
        aligned = _nz(data.get("pay_for_performance_aligned"), True)
        if not aligned:
            return "AGAINST", f"Pay-for-performance is not aligned over the trailing 3-year period; {policy_name} requires alignment.", evidence, sources, context

    return "FOR", f"No Say-on-Pay concerns flagged by {policy_name}.", evidence, sources, context


def _equity_plan(item, statement, rules, policy_name):
    cfg = rules.get("equity_plan", {})
    data, sources, context = _split(statement.get("equity_plan"))
    evidence = data

    max_dilution = cfg.get("max_dilution_pct")
    dilution = _nz(data.get("expected_dilution_pct"), 0)
    if max_dilution is not None and dilution > max_dilution:
        return "AGAINST", f"Total potential dilution of {dilution}% exceeds the {max_dilution}% threshold set by {policy_name}.", evidence, sources, context

    max_burn = cfg.get("max_burn_rate_pct")
    burn = _nz(data.get("three_year_avg_burn_rate_pct"), 0)
    if max_burn is not None and burn > max_burn:
        return "AGAINST", f"3-year avg burn rate of {burn}% exceeds the {max_burn}% threshold set by {policy_name}.", evidence, sources, context

    return "FOR", f"Dilution and burn rate within thresholds set by {policy_name}.", evidence, sources, context


def _shareholder_environmental(item, statement, rules, policy_name):
    cfg = rules.get("shareholder_environmental", {})
    for_topics = set(cfg.get("for_topics", []))
    raw = statement.get("shareholder_proposals", {}).get(item.get("subject_key"), {})
    data, sources, context = _split(raw)
    evidence = data
    topic = data.get("topic", "")
    if topic in for_topics:
        return "FOR", f"{policy_name} supports proposals on {topic}.", evidence, sources, context
    return "ABSTAIN", f"E&S topic {topic!r} does not match a coded {policy_name} rule; flag for manual review.", evidence, sources, context


def _shareholder_governance(item, statement, rules, policy_name):
    cfg = rules.get("shareholder_governance", {})
    for_topics = set(cfg.get("for_topics", []))
    against_topics = set(cfg.get("against_topics", []))
    raw = statement.get("shareholder_proposals", {}).get(item.get("subject_key"), {})
    data, sources, context = _split(raw)
    evidence = data
    topic = data.get("topic", "")
    if topic in for_topics:
        return "FOR", f"{policy_name} supports proposals on {topic}.", evidence, sources, context
    if topic in against_topics:
        return "AGAINST", f"{policy_name} opposes proposals on {topic}.", evidence, sources, context
    return "ABSTAIN", f"Governance topic {topic!r} does not match a coded {policy_name} rule; flag for manual review.", evidence, sources, context


def _default_handler(item, statement, rules, policy_name):
    return "ABSTAIN", f"Proposal type {item.get('type')!r} not covered by {policy_name}; flag for manual review.", {}, {}, ""


_HANDLERS = {
    "director_election":         _director_election,
    "auditor_ratification":      _auditor_ratification,
    "say_on_pay":                _say_on_pay,
    "equity_plan":               _equity_plan,
    "shareholder_environmental": _shareholder_environmental,
    "shareholder_governance":    _shareholder_governance,
}
