import { useRef, useState } from "react";
import { api } from "../api";

export default function PolicyDrawer({ markdown, onClose, onPolicyChanged }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [shown, setShown] = useState(markdown);
  const fileRef = useRef(null);

  const pick = () => fileRef.current?.click();

  const upload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const result = await api.importPolicy(file);
      setShown(result.markdown);
      onPolicyChanged?.(result);
    } catch (ex) {
      setErr(ex.message || String(ex));
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  };

  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-topbar">
          <input
            type="file"
            accept=".pdf,application/pdf"
            ref={fileRef}
            onChange={upload}
            style={{ display: "none" }}
          />
          <button className="close" onClick={pick} disabled={busy}>
            {busy ? "Reading PDF…" : "Import Proxy Voting Policy"}
          </button>
          <button className="close" onClick={onClose}>Close ✕</button>
        </div>
        {err && <div className="errata" style={{ margin: "0 32px" }}>Import failed — {err}</div>}
        <div className="drawer-content">
          <h1>Proxy Voting Policy<span className="red">.</span></h1>
          <div className="body">{shown}</div>
        </div>
      </div>
    </div>
  );
}
