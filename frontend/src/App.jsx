import { useEffect, useState } from "react";
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
    api.recommendations(ticker).then(setBallot).catch((e) => setError(e.message));
  };

  const openPolicy = () => {
    api.policy().then((p) => setPolicyMd(p.markdown)).catch((e) => setError(e.message));
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

          {selectedFund && !ballot && (
            <>
              <h1 className="display-h">
                Holdings<span className="alt">.</span>
              </h1>

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

      {policyMd && <PolicyDrawer markdown={policyMd} onClose={() => setPolicyMd(null)} />}
    </>
  );
}
