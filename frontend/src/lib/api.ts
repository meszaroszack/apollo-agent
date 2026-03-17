const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API error");
  }
  return res.json();
}

// ── Session ──────────────────────────────────────────────────────────────────

export interface SessionCreatePayload {
  kalshi_key_id: string;
  kalshi_private_key: string;
  perplexity_api_key?: string;
  balldontlie_api_key?: string;
  bankroll_usd: number;
  dry_run: boolean;
}

export const createSession = (payload: SessionCreatePayload) =>
  request<{ session_id: string; dry_run: boolean; sentiment_enabled: boolean }>("/api/session", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getSession = (sid: string) =>
  request<{
    session_id: string;
    dry_run: boolean;
    bankroll_usd: number;
    halted: boolean;
    halt_reason: string | null;
    sentiment_enabled: boolean;
    recon_status: string;
  }>(`/api/session/${sid}`);

// ── Markets ──────────────────────────────────────────────────────────────────

export const getMarkets = (sid: string, event_ticker?: string) =>
  request<{ markets: any[] }>(`/api/markets/${sid}${event_ticker ? `?event_ticker=${event_ticker}` : ""}`);

// ── Analysis & Trading ────────────────────────────────────────────────────────

export interface AnalyzePayload {
  session_id: string;
  market_ticker: string;
  team_a_id: number;
  team_a_name: string;
  team_b_id: number;
  team_b_name: string;
  p_market_a: number;
}

export const analyzeMatchup = (payload: AnalyzePayload) =>
  request<any>("/api/analyze", { method: "POST", body: JSON.stringify(payload) });

export const executeTrade = (payload: AnalyzePayload) =>
  request<any>("/api/trade", { method: "POST", body: JSON.stringify(payload) });

// ── Portfolio ─────────────────────────────────────────────────────────────────

export const getPortfolio = (sid: string) =>
  request<{ balance: any; positions: any }>(`/api/portfolio/${sid}`);

export const getLedgerBalance = (sid: string) =>
  request<{ balance_cents: number; balance_usd: number; double_entry_valid: boolean }>(
    `/api/ledger/balance/${sid}`
  );

export const getReconciliation = (sid: string) =>
  request<any>(`/api/reconciliation/${sid}`);

export const getDecisions = (sid: string, limit = 50) =>
  request<any[]>(`/api/decisions/${sid}?limit=${limit}`);

export const getOrderbook = (sid: string, ticker: string) =>
  request<any>(`/api/orderbook/${sid}/${ticker}`);
