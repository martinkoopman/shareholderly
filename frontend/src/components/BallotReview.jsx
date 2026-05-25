import { useState } from "react";
import { api } from "../api";

const FIELD_LABEL = {
  director: "Director",
  independent: "Independent",
  tenure_years: "Tenure (yrs)",
  attendance_pct: "Attendance",
  other_public_boards: "Other public boards",
  committees: "Committees",
  firm: "Audit firm",
  audit_fees_usd: "Audit fees",
  non_audit_fees_usd: "Non-audit fees",
  ceo_pay_usd: "CEO pay",
  ceo_pay_ratio: "CEO pay ratio",
  pay_for_performance_aligned: "Pay-for-performance aligned",
  expected_dilution_pct: "Expected dilution",
  three_year_avg_burn_rate_pct: "3-yr avg burn rate",
  topic: "Topic",
  proponent: "Proponent",
  summary: "Summary",
  board_position: "Board position",
};

function formatValue(v, k) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.length ? v.join(", ") : "—";
  if (typeof v === "number") {
    const num = Math.abs(v) >= 1000 ? v.toLocaleString() : String(v);
    if (k && k.endsWith("_usd")) return "$" + num;
    if (k && k.endsWith("_pct")) return num + "%";
    if (k && k.endsWith("_ratio")) return num + "x";
    return num;
  }
  if (typeof v === "string") {
    // Honor pre-formatted strings (e.g. "≥75%"); append a unit only if missing.
    if (k && k.endsWith("_usd") && !v.includes("$")) return "$" + v;
    if (k && k.endsWith("_pct") && !v.includes("%")) return v + "%";
    if (k && k.endsWith("_ratio") && !v.endsWith("x")) return v + "x";
    return v;
  }
  return String(v);
}

function sourceUrl(proxyUrl, quote /* context unused — see comment */) {
  if (!proxyUrl || !quote) return null;
  // Collapse all whitespace runs (incl. newlines) to a single space.
  // Browsers normalise whitespace in the visible page text before matching, but
  // they do NOT normalise the URL's text fragment itself — a literal %0A in the
  // URL won't match a rendered space. Quotes that span <p> boundaries inside a
  // table cell come back with embedded newlines; this strips those so the match
  // works.
  const cleanQuote = quote.replace(/\s+/g, " ").trim();
  // We tried two forms of "context anchoring" and both lose on SEC layouts:
  //   - prefix syntax (`text=ctx-,quote`) requires the prefix to be in the same
  //     block as the quote; SEC director bios put the name and the data in
  //     separate <p> tags, so the match fails and the browser lands at the top.
  //   - range syntax (`text=ctx,quote`) tolerates intervening blocks BUT scrolls
  //     to the FIRST occurrence of the context. Director names appear 10+ times
  //     (tables of contents, summaries) before the bio, producing a giant
  //     highlighted range landing the user in the wrong section.
  // In practice almost every quote is already unique on its own (e.g.
  // "Director since 2011" appears exactly once). Plain text fragment wins.
  return `${proxyUrl}#:~:text=${encodeURIComponent(cleanQuote)}`;
}

const TYPE_LABEL = {
  director_election: "Election to the Board",
  auditor_ratification: "Ratification of Auditor",
  say_on_pay: "Advisory · Executive Compensation",
  equity_plan: "Equity-Based Compensation Plan",
  shareholder_environmental: "Shareholder Proposal · Environmental",
  shareholder_governance: "Shareholder Proposal · Governance",
  other: "Other Business",
};

function summarize(recs) {
  const counts = { FOR: 0, AGAINST: 0, ABSTAIN: 0 };
  let disagreements = 0;
  for (const r of recs) {
    counts[r.vote] = (counts[r.vote] || 0) + 1;
    if (r.vote !== r.board_recommendation) disagreements++;
  }
  return { counts, disagreements };
}

function EvidenceTable({ evidence, sources, context, proxyUrl }) {
  const entries = Object.entries(evidence || {}).filter(([k]) => !k.startsWith("_"));
  if (!entries.length) return <div className="evidence-empty">No data extracted for this item.</div>;
  return (
    <table className="evidence-table">
      <thead>
        <tr>
          <th>Field</th>
          <th>Value</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([k, v]) => {
          const quote = sources?.[k];
          const href = sourceUrl(proxyUrl, quote, context);
          const tip = quote
            ? (context
                ? `"${quote}" — opens the filing scrolled to this phrase (anchored to "${context}")`
                : `"${quote}" — opens the filing scrolled to this phrase`)
            : null;
          return (
            <tr key={k}>
              <td className="ek">{FIELD_LABEL[k] || k}</td>
              <td className="ev">{formatValue(v, k)}</td>
              <td className="es">
                {href ? (
                  <a href={href} target="_blank" rel="noreferrer" title={tip}>
                    ↗ jump to source
                  </a>
                ) : (
                  <span className="es-none">—</span>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Entry({ r, idx, proxyUrl }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const disagrees = r.vote !== r.board_recommendation;
  return (
    <div className={`entry ${disagrees ? "disagree" : ""}`}>
      <div className="num-cell">{String(idx + 1).padStart(2, "0")}</div>

      <div className="body-cell">
        <div className="kicker">
          {TYPE_LABEL[r.type] || r.type}
          {r.ai_assisted && (
            <span className="ai-tag" title="No coded rule matched this proposal; vote derived from a Claude case-by-case analysis against the policy markdown.">
              AI · policy
            </span>
          )}
        </div>
        <h3 className="entry-title">{r.title}</h3>
        <p className="rationale">{r.rationale}</p>
        <button
          className="evidence-toggle"
          onClick={() => setShowEvidence(!showEvidence)}
        >
          {showEvidence ? "HIDE EVIDENCE" : "SHOW EVIDENCE FROM STATEMENT"}
        </button>
        {showEvidence && (
          <div className="evidence-panel">
            <EvidenceTable
              evidence={r.evidence}
              sources={r.evidence_sources}
              context={r.evidence_context}
              proxyUrl={proxyUrl}
            />
          </div>
        )}
      </div>

      <div className="verdict-cell">
        <div className="vlabel">Our vote</div>
        <div className={`vword ${r.vote}`}>{r.vote}</div>
        <div className="board">Board · <b>{r.board_recommendation}</b></div>
      </div>
    </div>
  );
}

const longDate = (s) => {
  if (!s) return null;
  const d = new Date(s);
  if (isNaN(d)) return s;
  return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
};

export default function BallotReview({ data, onBack, onRefreshed }) {
  const [refreshing, setRefreshing] = useState(false);
  const [refreshErr, setRefreshErr] = useState(null);

  const handleRefresh = async () => {
    setRefreshing(true);
    setRefreshErr(null);
    try {
      await api.refresh(data.ticker);
      const fresh = await api.recommendations(data.ticker);
      onRefreshed(fresh);
    } catch (e) {
      setRefreshErr(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  const { counts, disagreements } = summarize(data.recommendations);
  const total = data.recommendations.length;

  return (
    <div>
      <div className="toolbar">
        <button className="btn ghost" onClick={onBack}>← Back to register</button>
        <div className="action-bar">
          <a
            href={data.proxy_statement_url}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "none" }}
          >
            <button className="btn ghost">Original filing ↗</button>
          </a>
          <button
            className="btn primary"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? (
              <span className="dot">Dispatching</span>
            ) : (
              "Refresh from EDGAR"
            )}
          </button>
        </div>
      </div>

      {refreshErr && <div className="errata">Refresh failed — {refreshErr}</div>}

      <h1 className="display-h">
        {data.company_name.replace(/, Inc\.?$/i, "").replace(/ Corporation$/i, "")}
        {/, Inc\.?$/i.test(data.company_name) && <span className="of">, Inc.</span>}
        {/ Corporation$/i.test(data.company_name) && <span className="of"> Corp.</span>}
        <span className="alt">.</span>
      </h1>

      {data.meeting_date && (
        <div style={{ marginTop: 14, marginBottom: 28, fontSize: 14, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          {longDate(data.meeting_date)} · {data.ticker}
        </div>
      )}

      <div className="display-sub">
        <div className="cell">
          <div className="l">Items on card</div>
          <div className="v">{total}</div>
        </div>
        <div className="cell">
          <div className="l">For</div>
          <div className="v green">{counts.FOR || 0}</div>
        </div>
        <div className="cell">
          <div className="l">Against</div>
          <div className="v red">{counts.AGAINST || 0}</div>
        </div>
        <div className="cell">
          <div className="l">Split with board</div>
          <div className="v">{disagreements} <small>/ {total}</small></div>
        </div>
      </div>

      <div className="tbl-h">
        <div className="l">Ballot items</div>
        <div className="r">{disagreements} vote{disagreements === 1 ? "" : "s"} against management</div>
      </div>

      <div className="entries">
        {data.recommendations.map((r, i) => (
          <Entry key={r.item_id} r={r} idx={i} proxyUrl={data.proxy_statement_url} />
        ))}
      </div>
    </div>
  );
}
