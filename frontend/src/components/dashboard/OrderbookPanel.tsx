"use client";

import { useEffect, useState } from "react";
import { getOrderbook } from "@/lib/api";

export default function OrderbookPanel({ sessionId, ticker }: { sessionId: string; ticker: string }) {
  const [book, setBook] = useState<any>(null);

  useEffect(() => {
    if (!ticker || !sessionId) return;
    const fetch = async () => {
      try {
        const data = await getOrderbook(sessionId, ticker);
        setBook(data);
      } catch {}
    };
    fetch();
    const iv = setInterval(fetch, 2000);
    return () => clearInterval(iv);
  }, [ticker, sessionId]);

  const maxQty = book
    ? Math.max(
        ...Object.values(book.yes_bids || {}).map(Number),
        ...Object.values(book.yes_asks || {}).map(Number),
        1
      )
    : 1;

  return (
    <div className="panel" style={{ padding: "12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
        <div className="text-xs font-mono" style={{ color: "var(--accent-blue)", letterSpacing: "0.1em" }}>
          ORDERBOOK
        </div>
        {book && (
          <div style={{ fontSize: "10px", color: "var(--text-muted)" }}>
            {ticker || "—"} · mid={book.mid_price?.toFixed(1)}¢ · sprd={book.spread}¢
          </div>
        )}
      </div>

      {!ticker ? (
        <div style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", padding: "20px 0" }}>
          Enter a market ticker above
        </div>
      ) : !book ? (
        <div style={{ color: "var(--text-muted)", fontSize: "11px", textAlign: "center", padding: "20px 0" }}>
          Waiting for live data...
        </div>
      ) : (
        <div>
          {/* Column headers */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 2fr", gap: "4px", fontSize: "9px", color: "var(--text-muted)", marginBottom: "6px", letterSpacing: "0.1em" }}>
            <span>PRICE</span><span>QTY</span><span>DEPTH</span>
          </div>

          {/* Asks (sell side) */}
          <div style={{ marginBottom: "2px", fontSize: "10px", color: "var(--text-muted)", letterSpacing: "0.1em" }}>ASK</div>
          {Object.entries(book.yes_asks || {})
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
            ))}

          {/* Spread indicator */}
          <div style={{ borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", padding: "3px 0", margin: "4px 0", textAlign: "center", fontSize: "10px", color: "var(--accent-amber)" }}>
            MID {book.mid_price?.toFixed(1) || "—"}¢ · SPREAD {book.spread != null ? `${book.spread}¢` : "—"}
          </div>

          {/* Bids (buy side) */}
          <div style={{ marginBottom: "2px", fontSize: "10px", color: "var(--text-muted)", letterSpacing: "0.1em" }}>BID</div>
          {Object.entries(book.yes_bids || {})
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
            ))}
        </div>
      )}
    </div>
  );
}
