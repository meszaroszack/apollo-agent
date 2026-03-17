"""
Apollo-Agent FastAPI Server
"""

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apollo.alpha_engine import AlphaEngine, BallDontLieClient
from apollo.kalshi_client import KalshiClient
from apollo.kelly import KellySizer
from apollo.orderbook import OrderbookManager
from apollo.reconciliation import LedgerEngine, ReconciliationManager
from apollo.sentiment import SentimentGuardrail
from apollo.signer import KalshiSigner
from apollo.trade_engine import TradeEngine

log = logging.getLogger("apollo.main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

_sessions: dict[str, dict] = {}
_pool: Optional[asyncpg.Pool] = None
_db_ready: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool, _db_ready
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        log.warning(
            "DATABASE_URL not set — running without database. "
            "Session creation will fail until DATABASE_URL is configured."
        )
    else:
        try:
            _pool = await asyncpg.create_pool(db_url, min_size=2, max_size=10)
            _db_ready = True
            log.info("PostgreSQL pool created successfully")
        except Exception as exc:
            log.error("Failed to connect to PostgreSQL: %s", exc)
            log.error("DATABASE_URL was: %s", db_url[:40] + "..." if len(db_url) > 40 else db_url)
            # Don't crash — let the server start so /api/health responds
    yield
    if _pool:
        await _pool.close()
        log.info("PostgreSQL pool closed")


app = FastAPI(
    title="Apollo-Agent: Bracket Edition",
    description="Institutional HFT for Kalshi NCAAB prediction markets",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    kalshi_key_id: str
    kalshi_private_key: str
    perplexity_api_key: Optional[str] = None
    balldontlie_api_key: Optional[str] = None
    bankroll_usd: float = Field(1000.0, ge=10.0)
    dry_run: bool = True


class AnalyzeRequest(BaseModel):
    session_id: str
    market_ticker: str
    team_a_id: int
    team_a_name: str
    team_b_id: int
    team_b_name: str
    p_market_a: float = Field(..., ge=0.0, le=1.0)


class TradeRequest(BaseModel):
    session_id: str
    market_ticker: str
    team_a_id: int
    team_a_name: str
    team_b_id: int
    team_b_name: str
    p_market_a: float = Field(..., ge=0.0, le=1.0)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session(session_id: str) -> dict:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return _sessions[session_id]


async def _build_session(req: SessionCreate, session_id: str) -> dict:
    if not _db_ready or _pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database not connected. Check DATABASE_URL environment variable."
        )

    signer = KalshiSigner(req.kalshi_key_id, req.kalshi_private_key)
    kalshi = KalshiClient(signer)
    bdl = BallDontLieClient(req.balldontlie_api_key) if req.balldontlie_api_key else None
    alpha = AlphaEngine(bdl, season=2026)
    sentiment = SentimentGuardrail(req.perplexity_api_key)
    sizer = KellySizer(req.bankroll_usd)
    ledger = LedgerEngine(_pool)
    await ledger.initialize()

    async def halt_callback(reason: str):
        log.critical("HALT for session %s: %s", session_id, reason)
        if session_id in _sessions:
            _sessions[session_id]["halted"] = True
            _sessions[session_id]["halt_reason"] = reason

    recon = ReconciliationManager(ledger, signer, _pool, halt_callback)
    recon.start()

    engine = TradeEngine(alpha, sentiment, sizer, kalshi, ledger, recon, req.dry_run)
    ob_manager = OrderbookManager(signer, [], None)
    await ob_manager.start()

    return {
        "session_id": session_id,
        "signer": signer,
        "kalshi": kalshi,
        "bdl": bdl,
        "alpha": alpha,
        "sentiment": sentiment,
        "sizer": sizer,
        "ledger": ledger,
        "recon": recon,
        "engine": engine,
        "ob_manager": ob_manager,
        "dry_run": req.dry_run,
        "bankroll_usd": req.bankroll_usd,
        "halted": False,
        "halt_reason": None,
        "ws_clients": set(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "db_ready": _db_ready,
    }


@app.post("/api/session")
async def create_session(req: SessionCreate):
    session_id = str(uuid.uuid4())
    try:
        ctx = await _build_session(req, session_id)
        _sessions[session_id] = ctx
        return {
            "session_id": session_id,
            "dry_run": req.dry_run,
            "sentiment_enabled": ctx["sentiment"].is_enabled,
            "status": "active",
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Session creation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    ctx = _get_session(session_id)
    return {
        "session_id": session_id,
        "dry_run": ctx["dry_run"],
        "bankroll_usd": ctx["bankroll_usd"],
        "halted": ctx["halted"],
        "halt_reason": ctx["halt_reason"],
        "sentiment_enabled": ctx["sentiment"].is_enabled,
        "recon_status": ctx["recon"].status,
    }


@app.get("/api/markets/{session_id}")
async def get_markets(session_id: str, event_ticker: Optional[str] = None):
    ctx = _get_session(session_id)
    try:
        data = await ctx["kalshi"].get_markets(event_ticker=event_ticker, limit=50)
        return data
    except Exception as exc:
        log.error("Kalshi get_markets failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Kalshi API error: {exc}")


@app.get("/api/orderbook/{session_id}/{ticker}")
async def get_orderbook(session_id: str, ticker: str):
    ctx = _get_session(session_id)
    ob = ctx["ob_manager"]
    if ticker not in ob._tickers:
        ob.subscribe(ticker)
    book = ob.get_book(ticker)
    if not book:
        raise HTTPException(status_code=404, detail="Orderbook not yet populated")
    return book.to_dict()


@app.get("/api/orderbooks/{session_id}")
async def get_all_orderbooks(session_id: str):
    ctx = _get_session(session_id)
    return ctx["ob_manager"].all_books()


@app.post("/api/analyze")
async def analyze_matchup(req: AnalyzeRequest):
    ctx = _get_session(req.session_id)
    signal = await ctx["alpha"].analyze_matchup(
        req.team_a_id, req.team_a_name,
        req.team_b_id, req.team_b_name,
        req.p_market_a,
    )
    side = "NO" if signal.signal in ("NO_A", "NO_B") else "YES"
    trade_on_a = signal.signal in ("NO_A", "YES_A")
    p_true = signal.p_true_a if trade_on_a else signal.p_true_b
    p_market = req.p_market_a if trade_on_a else (1.0 - req.p_market_a)
    sizing = ctx["sizer"].size(p_true, p_market, side=side)

    sentiment = None
    if ctx["sentiment"].is_enabled and signal.signal != "NEUTRAL":
        primary = req.team_a_name if trade_on_a else req.team_b_name
        s = await ctx["sentiment"].evaluate(req.team_a_name, req.team_b_name, primary)
        sentiment = {"score": s.score, "should_abort": s.should_abort, "reason": s.reason, "summary": s.summary}

    return {
        "signal": signal.signal,
        "edge": signal.edge,
        "rationale": signal.rationale,
        "p_true_a": signal.p_true_a,
        "p_true_b": signal.p_true_b,
        "divergence_a": signal.divergence_a,
        "divergence_b": signal.divergence_b,
        "sizing": {
            "should_trade": sizing.should_trade,
            "bet_on": sizing.bet_on,
            "position_dollars": sizing.position_dollars,
            "position_cents": sizing.position_cents,
            "kelly_full": sizing.kelly_full,
            "kelly_fractional": sizing.kelly_fractional,
            "edge": sizing.edge,
            "rationale": sizing.rationale,
        },
        "sentiment": sentiment,
    }


@app.post("/api/trade")
async def execute_trade(req: TradeRequest):
    ctx = _get_session(req.session_id)
    if ctx["halted"]:
        raise HTTPException(status_code=503, detail="Trading halted: " + str(ctx["halt_reason"]))

    decision = await ctx["engine"].evaluate_and_trade(
        req.market_ticker,
        req.team_a_id, req.team_a_name,
        req.team_b_id, req.team_b_name,
        req.p_market_a,
    )
    return {
        "executed": decision.executed,
        "order_id": decision.order_id,
        "abort_reason": decision.abort_reason,
        "timestamp": decision.timestamp,
        "signal": decision.matchup_signal.signal if decision.matchup_signal else None,
        "sizing": {
            "position_dollars": decision.sizing.position_dollars if decision.sizing else None,
            "bet_on": decision.sizing.bet_on if decision.sizing else None,
        } if decision.sizing else None,
    }


@app.get("/api/portfolio/{session_id}")
async def get_portfolio(session_id: str):
    ctx = _get_session(session_id)
    try:
        balance = await ctx["kalshi"].get_balance()
        positions = await ctx["kalshi"].get_positions()
        return {"balance": balance, "positions": positions}
    except Exception as exc:
        log.error("Kalshi get_portfolio failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Kalshi API error: {exc}")


@app.get("/api/ledger/balance/{session_id}")
async def get_ledger_balance(session_id: str):
    ctx = _get_session(session_id)
    cents = await ctx["ledger"].get_cash_balance_cents()
    valid = await ctx["ledger"].verify_double_entry()
    return {
        "balance_cents": cents,
        "balance_usd": cents / 100,
        "double_entry_valid": valid,
    }


@app.get("/api/reconciliation/{session_id}")
async def get_reconciliation(session_id: str):
    ctx = _get_session(session_id)
    if not _pool:
        return {"status": "No database connection"}
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM reconciliation_log ORDER BY id DESC LIMIT 1"
        )
    return dict(row) if row else {"status": "No reconciliation run yet"}


@app.get("/api/decisions/{session_id}")
async def get_decisions(session_id: str, limit: int = 50):
    ctx = _get_session(session_id)
    return ctx["engine"].recent_decisions(limit)


@app.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    if session_id not in _sessions:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept()
    ctx = _sessions[session_id]
    ctx["ws_clients"].add(websocket)

    def push_book_update(ticker: str, book_dict: dict):
        asyncio.create_task(
            _broadcast_to_session(session_id, {"type": "orderbook", "ticker": ticker, "data": book_dict})
        )
    ctx["ob_manager"]._on_update = push_book_update

    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        ctx["ws_clients"].discard(websocket)


async def _broadcast_to_session(session_id: str, msg: dict) -> None:
    ctx = _sessions.get(session_id)
    if not ctx:
        return
    dead = set()
    for ws in ctx["ws_clients"]:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.add(ws)
    ctx["ws_clients"] -= dead
