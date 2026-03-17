"use client";

import { useEffect, useState } from "react";
import { getOrderbook } from "@/lib/api";

export default function OrderbookPanel({ sessionId, ticker }: { sessionId: string; ticker: string }) {
  const [book, setBook] = useState<any>(null);
  const [side, setSide] = useState<"yes" | "no">("yes");

  useEffect(() => {
    if (!ticker || !sessionId) { setBook(null); return; }
    const fetchBook = async () => {
      try {
        const data = await getOrderbook(sessionId, ticker);
        setBook(data);
      } catch {
        // 404 = orderbook not yet populated, keep polling
      }
    };
    fetchBook();
    const iv = setInterval(fetchBook, 2000);
    return () => clearInterval(iv);
  }, [ticker, sessionId]);

  const bids = side === "yes" ? book?.yes_bids : book?.no_bids;
  const asks = side === "yes" ? book?.yes_asks : book?.no_asks;

  const maxQty = book
    ? Math.max(
        ...Object.values(bids || {}).map(Number),
        ...Object.values(asks || {}).map(Number),
        1
      )
    : 1;

  const tabStyle = (active: boolean) => ({
    fontSize: "10px",
    fontFamily: "monospace",
    padding: "2px 8px",
    border: "1px solid var(--border)",
    borderRadius: "3px",
    cursor: "pointer" as const,
    background: active ? "var(--bg-elevated)" : "transparent",
    color: active ? "var(--text-primary)" : "var(--text-muted)",
    fontWeight: active ? "600" as const : "400" as const,
  });

  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <div className="text-xs font-mono" style={{ color: "var(--accent-blue)", letterSpacing: "0.1em" }}>
            ORDERBOOK
          </div>
          {book && (
            <div style={{ display: "flex", gap: "4px" }}>
              <button onClick={() => setSide("yes")} style={tabStyle(side === "yes")}>YES</button>
              <button onClick={() => setSide("no")} style={tabStyle(side === "no")}>NO</button>
            </div>
          )}
        </div>
        {book && (
          <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
            {ticker || "—"} · mid={book.mid_price?.toFixed(1)}¢ · sprd={book.spread}¢
          </div>
        )}
      </div>

      {!ticker ? (
        <div style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", padding: "20px 0" }}>
          Select a market above
        </div>
      ) : !book ? (
        <div style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", padding: "20px 0" }}>
          Waiting for orderbook data...
        </div>
      ) : (
        <div>
          {/* Column headers */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: "4px", fontSize: "9px", color: "var(--text-muted)", marginBottom: "6px", letterSpacing: "0.1em" }}>
            <span>PRICE</span><span>QTY</span><span>DEPTH</span>
          </div>

          {/* Asks (sell side) */}
          <div style={{ marginBottom: "2px", fontSize: "10px", color: "var(--text-muted)", letterSpacing: "0.1em" }}>
            {side.toUpperCase()} ASK
          </div>
          {Object.entries(asks || {}).length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: "10px", padding: "4px 0" }}>No asks</div>
          ) : (
            Object.entries(asks || {})
              .sort(([a], [b]) => Number(b) - Number(a))
              .slice(0, 5)
              .map(([price, qty]: any) => (
                <div key={`ask-${price}`} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: "4px", marginBottom: "2px", alignItems: "center" }}>
                  <span style={{ color: "var(--accent-red)", fontSize: "11px" }}>{price}¢</span>
                  <span style={{ color: "var(--text-secondary)", fontSize: "11px" }}>{qty}</span>
                  <div style={{ background: "var(--bg-elevated)", borderRadius: "2px", height: "6px", overflow: "hidden" }}>
                    <div style={{ width: `${(qty / maxQty) * 100}%`, height: "100%", background: "rgba(239,68,68,0.4)" }} />
                  </div>
                </div>
              ))
          )}

          {/* Spread indicator */}
          <div style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", padding: "3px 0", margin: "4px 0", textAlign: "center", fontSize: "10px", color: "var(--accent-amber)" }}>
            MID {book.mid_price?.toFixed(1) || "—"}¢ · SPREAD {book.spread != null ? `${book.spread}¢` : "—"}
          </div>

          {/* Bids (buy side) */}
          <div style={{ marginBottom: "2px", fontSize: "10px", color: "var(--text-muted)", letterSpacing: "0.1em" }}>
            {side.toUpperCase()} BID
          </div>
          {Object.entries(bids || {}).length === 0 ? (
            <div style={{ color: "var(--text-muted)", fontSize: "10px", padding: "4px 0" }}>No bids</div>
          ) : (
            Object.entries(bids || {})
              .sort(([a], [b]) => Number(b) - Number(a))
              .slice(0, 5)
              .map(([price, qty]: any) => (
                <div key={`bid-${price}`} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: "4px", marginBottom: "2px", alignItems: "center" }}>
                  <span style={{ color: "var(--accent-green)", fontSize: "11px" }}>{price}¢</span>
                  <span style={{ color: "var(--text-secondary)", fontSize: "11px" }}>{qty}</span>
                  <div style={{ background: "var(--bg-elevated)", borderRadius: "2px", height: "6px", overflow: "hidden" }}>
                    <div style={{ width: `${(qty / maxQty) * 100}%`, height: "100%", background: "rgba(0,208,132,0.4)" }} />
                  </div>
                </div>
              ))
          )}
        </div>
      )}
    </div>
  );
}
