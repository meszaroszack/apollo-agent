"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { useApolloStore } from "@/lib/store";
import {
  getSession, getPortfolio, getLedgerBalance,
  getReconciliation, getDecisions, analyzeMatchup, executeTrade,
  getMarkets, AnalyzePayload
} from "@/lib/api";
import PnLChart from "@/components/charts/PnLChart";
import DivergenceChart from "@/components/charts/DivergenceChart";
import OrderbookPanel from "@/components/dashboard/OrderbookPanel";
import DecisionLog from "@/components/dashboard/DecisionLog";

export default function DashboardPage() {
  const router = useRouter();
  const { sessionId, sessionConfig } = useApolloStore();

  const [session, setSession] = useState<any>(null);
  const [portfolio, setPortfolio] = useState<any>(null);
  const [ledger, setLedger] = useState<any>(null);
  const [recon, setRecon] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [markets, setMarkets] = useState<any[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [trading, setTrading] = useState(false);
  const [lastAnalysis, setLastAnalysis] = useState<any>(null);

  // Trade form state
  const [form, setForm] = useState({
    market_ticker: "",
    team_a_id: "",
    team_a_name: "",
    team_b_id: "",
    team_b_name: "",
    p_market_a: "0.50",
  });

  const refreshAll = async () => {
    if (!sessionId) return;
    try {
      const [s, p, l, r, d, m] = await Promise.allSettled([
        getSession(sessionId),
        getPortfolio(sessionId),
        getLedgerBalance(sessionId),
        getReconciliation(sessionId),
        getDecisions(sessionId, 50),
        getMarkets(sessionId, "kxncaambgame"),
      ]);
      if (s.status === "fulfilled") setSession(s.value);
      if (p.status === "fulfilled") setPortfolio(p.value);
      if (l.status === "fulfilled") setLedger(l.value);
      if (r.status === "fulfilled") setRecon(r.value);
      if (d.status === "fulfilled") setDecisions(d.value);
      if (m.status === "fulfilled") setMarkets(m.value?.markets || []);

      if (s.status === "fulfilled" && s.value.halted) {
        toast.error(`TRADING HALTED: ${s.value.halt_reason}`);
      }
    } catch {
      // silently absorb — polling will retry
    }
  };

  useEffect(() => {
    if (!sessionId) { router.replace("/onboarding"); return; }
    refreshAll();
    const iv = setInterval(refreshAll, 10000);
    return () => clearInterval(iv);
  }, [sessionId]);

  const handleAnalyze = async () => {
    if (!sessionId || !form.market_ticker) return;
    setAnalyzing(true);
    try {
      const payload: AnalyzePayload = {
        session_id: sessionId,
        market_ticker: form.market_ticker,
        team_a_id: parseInt(form.team_a_id),
        team_a_name: form.team_a_name,
        team_b_id: parseInt(form.team_b_id),
        team_b_name: form.team_b_name,
        p_market_a: parseFloat(form.p_market_a),
      };
      const result = await analyzeMatchup(payload);
      setLastAnalysis(result);
      toast.success(`Signal: ${result.signal} | Edge: ${(result.edge * 100).toFixed(2)}%`);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  const handleTrade = async () => {
    if (!sessionId || !form.market_ticker) return;
    setTrading(true);
    try {
      const payload: AnalyzePayload = {
        session_id: sessionId,
        market_ticker: form.market_ticker,
        team_a_id: parseInt(form.team_a_id),
        team_a_name: form.team_a_name,
        team_b_id: parseInt(form.team_b_id),
        team_b_name: form.team_b_name,
        p_market_a: parseFloat(form.p_market_a),
      };
      const result = await executeTrade(payload);
      if (result.executed) {
        toast.success(`Order submitted: ${result.order_id}`);
      } else {
        toast.info(`Trade skipped: ${result.abort_reason}`);
      }
      await refreshAll();
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setTrading(false);
    }
  };

  const signalColor = (sig: string) => {
    if (sig?.includes("NO")) return "var(--accent-red)";
    if (sig?.includes("YES")) return "var(--accent-green)";
    return "var(--text-muted)";
  };

  const inputStyle = {
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    color: "var(--text-primary)",
    outline: "none",
    padding: "6px 8px",
    fontSize: "12px",
    fontFamily: "monospace",
    borderRadius: "3px",
    width: "100%",
  };

  return (
    <div style={{ background: "var(--bg-base)", minHeight: "100vh", padding: "0" }}>
      {/* Top Bar */}
      <div style={{
        background: "var(--bg-panel)",
        borderBottom: "1px solid var(--border)",
        padding: "8px 16px",
        display: "flex",
        alignItems: "center",
        gap: "24px",
        position: "sticky",
        top: 0,
        zIndex: 100,
      }}>
        <div style={{ color: "var(--accent-green)", fontWeight: "700", letterSpacing: "0.15em", fontSize: "13px" }}>
          ◆ APOLLO-AGENT
        </div>

        <div className="live-pulse" style={{
          width: 6, height: 6, borderRadius: "50%",
          background: session?.halted ? "var(--accent-red)" : "var(--accent-green)"
        }} />

        <div style={{ display: "flex", gap: "24px", flex: 1 }}>
          {/* Balance */}
          <Stat label="LEDGER CASH" value={ledger ? `$${ledger.balance_usd?.toFixed(2)}` : "—"} />
          <Stat label="KALSHI BAL" value={portfolio ? `$${(portfolio.balance?.balance / 100)?.toFixed(2)}` : "—"} />
          <Stat label="RECON" value={recon?.status || "—"} color={recon?.status === "OK" ? "var(--accent-green)" : "var(--accent-red)"} />
          <Stat label="SIGNALS TODAY" value={decisions.filter(d => d.executed).length.toString()} />
          <Stat label="MODE" value={sessionConfig?.dryRun ? "SIM" : "LIVE"} color={sessionConfig?.dryRun ? "var(--accent-blue)" : "var(--accent-red)"} />
          <Stat label="SENTIMENT" value={sessionConfig?.sentimentEnabled ? "ON" : "OFF"} color={sessionConfig?.sentimentEnabled ? "var(--accent-purple)" : "var(--text-muted)"} />
        </div>

        <button
          onClick={() => { useApolloStore.getState().clearSession(); router.replace("/onboarding"); }}
          style={{
            fontSize: "11px", color: "var(--text-muted)", background: "none",
            border: "1px solid var(--border)", padding: "4px 10px", borderRadius: "3px",
            cursor: "pointer", fontFamily: "monospace",
          }}
        >
          DISCONNECT
        </button>
      </div>

      {/* Halt banner */}
      {session?.halted && (
        <div style={{
          background: "rgba(239,68,68,0.15)", border: "1px solid var(--accent-red)",
          padding: "8px 16px", color: "var(--accent-red)", fontSize: "12px", fontFamily: "monospace"
        }}>
          ⛔ TRADING HALTED — {session.halt_reason}
        </div>
      )}

      {/* Main grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 380px", gap: "8px", padding: "8px" }}>
        {/* Left col: Charts */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <PnLChart decisions={decisions} />
          <DivergenceChart decisions={decisions} />
        </div>

        {/* Middle col: Trade form + Analysis result */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {/* Trade Form */}
          <div className="panel" style={{ padding: "12px" }}>
            <div className="text-xs font-mono mb-3" style={{ color: "var(--accent-amber)", letterSpacing: "0.1em" }}>
              MATCHUP ANALYZER
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>MARKET TICKER</label>
                {markets.length > 0 ? (
                  <select
                    style={{ ...inputStyle, cursor: "pointer" }}
                    value={form.market_ticker}
                    onChange={e => {
                      const ticker = e.target.value;
                      const mkt = markets.find((m: any) => m.ticker === ticker);
                      setForm(f => ({
                        ...f,
                        market_ticker: ticker,
                        p_market_a: mkt?.yes_bid ? (mkt.yes_bid / 100).toFixed(2) : f.p_market_a,
                      }));
                    }}
                  >
                    <option value="">— select market —</option>
                    {markets.map((m: any) => (
                      <option key={m.ticker} value={m.ticker}>
                        {m.title || m.ticker}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input style={inputStyle} placeholder="kxncaambgame-26mar17..." value={form.market_ticker} onChange={e => setForm(f => ({ ...f, market_ticker: e.target.value }))} />
                )}
              </div>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>P_MARKET (YES team A)</label>
                <input style={inputStyle} type="number" step="0.01" min="0.01" max="0.99" value={form.p_market_a} onChange={e => setForm(f => ({ ...f, p_market_a: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>TEAM A NAME</label>
                <input style={inputStyle} placeholder="Duke" value={form.team_a_name} onChange={e => setForm(f => ({ ...f, team_a_name: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>TEAM A BDL ID</label>
                <input style={inputStyle} type="number" placeholder="1" value={form.team_a_id} onChange={e => setForm(f => ({ ...f, team_a_id: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>TEAM B NAME</label>
                <input style={inputStyle} placeholder="UNC" value={form.team_b_name} onChange={e => setForm(f => ({ ...f, team_b_name: e.target.value }))} />
              </div>
              <div>
                <label className="text-xs" style={{ color: "var(--text-secondary)" }}>TEAM B BDL ID</label>
                <input style={inputStyle} type="number" placeholder="2" value={form.team_b_id} onChange={e => setForm(f => ({ ...f, team_b_id: e.target.value }))} />
              </div>
            </div>

            <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                style={{
                  flex: 1, padding: "8px", fontSize: "11px", fontFamily: "monospace",
                  fontWeight: "700", letterSpacing: "0.1em",
                  background: "rgba(59,130,246,0.15)", border: "1px solid var(--accent-blue)",
                  color: "var(--accent-blue)", borderRadius: "3px", cursor: "pointer",
                }}
              >
                {analyzing ? "COMPUTING..." : "ANALYZE"}
              </button>
              <button
                onClick={handleTrade}
                disabled={trading || session?.halted}
                style={{
                  flex: 1, padding: "8px", fontSize: "11px", fontFamily: "monospace",
                  fontWeight: "700", letterSpacing: "0.1em",
                  background: session?.halted ? "var(--bg-elevated)" : sessionConfig?.dryRun ? "rgba(0,208,132,0.15)" : "rgba(239,68,68,0.2)",
                  border: `1px solid ${session?.halted ? "var(--border)" : sessionConfig?.dryRun ? "var(--accent-green)" : "var(--accent-red)"}`,
                  color: session?.halted ? "var(--text-muted)" : sessionConfig?.dryRun ? "var(--accent-green)" : "var(--accent-red)",
                  borderRadius: "3px", cursor: session?.halted ? "not-allowed" : "pointer",
                }}
              >
                {trading ? "SUBMITTING..." : sessionConfig?.dryRun ? "SIM TRADE" : "⚡ LIVE TRADE"}
              </button>
            </div>
          </div>

          {/* Analysis Result */}
          {lastAnalysis && (
            <div className="panel" style={{ padding: "12px" }}>
              <div className="text-xs font-mono mb-3" style={{ color: "var(--accent-green)", letterSpacing: "0.1em" }}>
                ALPHA SIGNAL
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", marginBottom: "10px" }}>
                <StatCard label="SIGNAL" value={lastAnalysis.signal} color={signalColor(lastAnalysis.signal)} />
                <StatCard label="EDGE" value={`${(lastAnalysis.edge * 100).toFixed(2)}%`} color="var(--accent-amber)" />
                <StatCard label="POSITION" value={lastAnalysis.sizing?.position_dollars ? `$${lastAnalysis.sizing.position_dollars.toFixed(2)}` : "—"} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "10px" }}>
                <StatCard label="P_TRUE_A" value={lastAnalysis.p_true_a?.toFixed(4)} />
                <StatCard label="P_MARKET_A" value={parseFloat(form.p_market_a).toFixed(4)} />
                <StatCard label="DIV_A" value={lastAnalysis.divergence_a?.toFixed(4)} color={lastAnalysis.divergence_a > 0.05 ? "var(--accent-red)" : "var(--text-secondary)"} />
                <StatCard label="KELLY_FULL" value={lastAnalysis.sizing?.kelly_full?.toFixed(4)} />
              </div>
              {lastAnalysis.sentiment && (
                <div style={{
                  padding: "8px", borderRadius: "3px",
                  background: lastAnalysis.sentiment.should_abort ? "rgba(239,68,68,0.1)" : "rgba(0,208,132,0.08)",
                  border: `1px solid ${lastAnalysis.sentiment.should_abort ? "var(--accent-red)" : "var(--border)"}`,
                }}>
                  <div className="text-xs" style={{ color: "var(--text-secondary)", marginBottom: "4px" }}>SENTIMENT</div>
                  <div className="text-xs" style={{ color: lastAnalysis.sentiment.should_abort ? "var(--accent-red)" : "var(--accent-green)" }}>
                    {lastAnalysis.sentiment.reason} · score={lastAnalysis.sentiment.score?.toFixed(2)}
                  </div>
                </div>
              )}
              <div className="text-xs mt-2" style={{ color: "var(--text-muted)", lineHeight: 1.6, wordBreak: "break-all" }}>
                {lastAnalysis.rationale}
              </div>
            </div>
          )}
        </div>

        {/* Right col: Orderbook + Decision log */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <OrderbookPanel sessionId={sessionId!} ticker={form.market_ticker} />
          <DecisionLog decisions={decisions} />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div style={{ fontSize: "9px", color: "var(--text-muted)", letterSpacing: "0.1em" }}>{label}</div>
      <div style={{ fontSize: "12px", color: color || "var(--text-primary)", fontWeight: "600" }}>{value}</div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value?: string; color?: string }) {
  return (
    <div style={{ background: "var(--bg-elevated)", padding: "6px 8px", borderRadius: "3px" }}>
      <div style={{ fontSize: "9px", color: "var(--text-muted)", letterSpacing: "0.1em", marginBottom: "2px" }}>{label}</div>
      <div style={{ fontSize: "13px", color: color || "var(--text-primary)", fontWeight: "600" }}>{value || "—"}</div>
    </div>
  );
}
