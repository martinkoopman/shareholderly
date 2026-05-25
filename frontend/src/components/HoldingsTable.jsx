const fmtUSD = (n) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const fmt = (n) => n.toLocaleString("en-US");

export default function HoldingsTable({ holdings, onPick }) {
  return (
    <>
      <div className="tbl-h">
        <div className="l">
          <span className="pre">01</span>Long-side positions
        </div>
        <div className="r">Click any line bearing a filing →</div>
      </div>

      <table className="t">
        <thead>
          <tr>
            <th style={{ width: 36 }}>#</th>
            <th style={{ width: 90 }}>Ticker</th>
            <th>Company</th>
            <th className="r" style={{ width: 130 }}>Shares</th>
            <th className="r" style={{ width: 180 }}>Position USD</th>
            <th className="r" style={{ width: 130 }}>Filing</th>
            <th className="r" style={{ width: 36 }}></th>
          </tr>
        </thead>
        <tbody>
          {holdings.map((h, i) => {
            const clickable = h.proxy_available;
            return (
              <tr
                key={h.ticker}
                className={clickable ? "clickable" : "muted"}
                onClick={() => clickable && onPick(h.ticker)}
              >
                <td>{String(i + 1).padStart(2, "0")}</td>
                <td className="tk">{h.ticker}</td>
                <td className="cm">{h.company_name}</td>
                <td className="r num">{fmt(h.shares)}</td>
                <td className="r num">{fmtUSD(h.value_usd)}</td>
                <td className="r">
                  <span className={`badge ${clickable ? "av" : "un"}`}>
                    {clickable ? "On file" : "Awaiting"}
                  </span>
                </td>
                <td className="r">
                  {clickable && <span className="arrow-cell">→</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

    </>
  );
}
