export default function PolicyDrawer({ markdown, onClose }) {
  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-topbar">
          <span></span>
          <button className="close" onClick={onClose}>Close ✕</button>
        </div>
        <div className="drawer-content">
          <h1>Proxy Voting Policy<span className="red">.</span></h1>
          <div className="body">{markdown}</div>
        </div>
      </div>
    </div>
  );
}
