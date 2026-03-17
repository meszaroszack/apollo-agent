"use client";

export default function DecisionLog({ decisions }: { decisions: any[] }) {
  const rows = [...decisions].reverse().slice(0, 30);

  return (
    <div className="panel" style={{ padding: "12px", flex: 1, overflow: "hidden" }}>
      <div className="text-xs font-mono mb-3" style={{ color: "var(--accent-purple)", letterSpacing: "0.1em" }}>
        DECISION LOG
      </div>
      <div style={{ overflowY: "auto", maxHeight: "400px" }}>
        {rows.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", padding: "20px 0" }}>
            No decisions yet — run ANALYZE or TRADE
          </div>
        ) : (
          rows.map((d, i) => (
            <DecisionRow key={i} decision={d} />
          ))
        )}
      </div>
    </div>
  );
}

function DecisionRow({ decision: d }: { decision: any }) {
  const isExecuted = d.executed;
  const isSkipped = d.abort_reason;
  const time = d.timestamp ? new Date(d.timestamp).toLocaleTimeString("en-US", { hour12: false }) : "—";

  const bgColor = isExecuted
    ? "rgba(0,208,132,0.06)"
    : isSkipped
    ? "rgba(239,68,68,0.06)"
    : "transparent";

  const borderColor = isExecuted
    ? "rgba(0,208,132,0.2)"
    : "rgba(239,68,68,0.15)";

  return (
    <div style={{
      padding: "6px 8px",
      marginBottom: "4px",
      borderRadius: "3px",
      background: bgColor,
      border: `1px solid ${borderColor}`,
      fontSize: "11px",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
        <span style={{ color: isExecuted ? "var(--accent-green)" : "var(--accent-red)", fontWeight: "700" }}>
          {isExecuted ? "●" : "○"} {d.signal || "—"}
        </span>
        <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>{time}</span>
      </div>
      <div style={{ color: "var(--text-secondary)", fontSize: "10px", marginBottom: "2px" }}>
        {isExecuted
          ? `${d.sizing?.bet_on || ""} $${d.sizing?.position_dollars?.toFixed(2) || "—"} · order=${d.order_id?.slice(-8) || "SIM"}`
          : d.abort_reason?.slice(0, 60) || ""}
      </div>
      {d.rationale && (
        <div style={{ color: "var(--text-muted)", fontSize: "9px", lineHeight: 1.5, fontFamily: "monospace", wordBreak: "break-all" }}>
          {d.rationale?.slice(0, 120)}
        </div>
      )}
    </div>
  );
}
