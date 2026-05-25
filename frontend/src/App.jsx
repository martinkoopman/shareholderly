import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import HoldingsTable from "./components/HoldingsTable.jsx";
import BallotReview from "./components/BallotReview.jsx";
import PolicyDrawer from "./components/PolicyDrawer.jsx";

export default function App() {
  const [funds, setFunds] = useState([]);
  const [selectedFund, setSelectedFund] = useState(null);
  const [holdings, setHoldings] = useState([]);
  const [ballot, setBallot] = useState(null);
  const [policyMd, setPolicyMd] = useState(null);
  const [error, setError] = useState(null);
  const [importingHoldings, setImportingHoldings] = useState(false);
  const [loadingTicker, setLoadingTicker] = useState(null);
  const csvRef = useRef(null);

  useEffect(() => {
    api.funds().then((fs) => {
      setFunds(fs);
      if (fs[0]) setSelectedFund(fs[0]);
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!selectedFund) return;
    setBallot(null);
    api.holdings(selectedFund.fund_id)
      .then(setHoldings)
      .catch((e) => setError(e.message));
  }, [selectedFund]);

  const openBallot = (ticker) => {
    setError(null);
    setLoadingTicker(ticker);
    api.recommendations(ticker)
      .then((data) => {
        setBallot(data);
        setLoadingTicker(null);
      })
      .catch((e) => {
        setError(e.message);
        setLoadingTicker(null);
      });
  };

  const openPolicy = () => {
    api.policy().then((p) => setPolicyMd(p.markdown)).catch((e) => setError(e.message));
  };

  const onHoldingsCsv = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedFund) return;
    setError(null);
    setImportingHoldings(true);
    try {
      const result = await api.importHoldings(selectedFund.fund_id, file);
      const fresh = await api.holdings(selectedFund.fund_id);
      setHoldings(fresh);
      if (result.rows_skipped) {
        setError(`Imported ${result.rows_inserted} rows; skipped ${result.rows_skipped} (${result.errors.slice(0, 2).join("; ")}).`);
      }
    } catch (ex) {
      setError(ex.message || String(ex));
    } finally {
      setImportingHoldings(false);
      e.target.value = "";
    }
  };

  return (
    <>
      <div className="topbar">
        <button
          className="seal"
          onClick={() => setBallot(null)}
          title="Back to holdings"
          style={{ background: "none", border: "none", padding: 0, cursor: "pointer", font: "inherit", color: "inherit" }}
        >
          <span className="x"></span>
          <b>Shareholderly</b>
        </button>
      </div>

      <div className="grid12">
        <aside className="index">
          <div className="section">
            <h2 className="section-h">Funds Under<br/>Coverage</h2>
            {funds.map((f) => (
              <button
                key={f.fund_id}
                className={`fund-item ${selectedFund?.fund_id === f.fund_id ? "active" : ""}`}
                onClick={() => setSelectedFund(f)}
              >
                <div className="nm">{f.name}</div>
              </button>
            ))}
          </div>

          <div className="section">
            <h2 className="section-h">Reference</h2>
            <button className="fund-item" onClick={openPolicy}>
              <div className="nm">Proxy Voting Policy</div>
            </button>
          </div>
        </aside>

        <main className="doc">
          {error && <div className="errata">{error}</div>}

          {!selectedFund && <div className="empty">Select a fund to begin.</div>}

          {loadingTicker && !ballot && (
            <div className="loading-ballot">
              <div className="spin"></div>
              <div className="loading-title">Loading {loadingTicker} ballot…</div>
              <div className="loading-sub">Applying policy and running case-by-case analysis on novel proposals. This may take 10–30 seconds.</div>
            </div>
          )}

          {selectedFund && !ballot && !loadingTicker && (
            <>
              <div className="page-h-row">
                <h1 className="display-h">
                  Holdings<span className="alt">.</span>
                </h1>
                <div className="page-h-actions">
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    ref={csvRef}
                    onChange={onHoldingsCsv}
                    style={{ display: "none" }}
                  />
                  <button
                    className="btn ghost"
                    onClick={() => csvRef.current?.click()}
                    disabled={importingHoldings}
                  >
                    {importingHoldings ? "Importing…" : "Import holdings CSV ↑"}
                  </button>
                </div>
              </div>

              <HoldingsTable
                holdings={holdings}
                onPick={openBallot}
              />
            </>
          )}

          {ballot && (
            <BallotReview
              data={ballot}
              onBack={() => setBallot(null)}
              onRefreshed={setBallot}
            />
          )}
        </main>
      </div>

      {policyMd && (
        <PolicyDrawer
          markdown={policyMd}
          onClose={() => setPolicyMd(null)}
          onPolicyChanged={() => {
            // Imported policy: drop any open ballot so the next view re-fetches
            // recommendations under the new rules.
            setBallot(null);
          }}
        />
      )}
    </>
  );
}
