# ◆ Apollo-Agent: Bracket Edition

**Institutional-grade quantitative trading system for Kalshi NCAAB prediction market contracts.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Apollo-Agent Stack                           │
│                                                                     │
│  ┌─────────────────────────────────────┐                            │
│  │  Next.js 16 + Tailwind v4 Dashboard │  Bloomberg-style terminal  │
│  │  • Secure Onboarding (key upload)   │                            │
│  │  • P&L + Divergence ApexCharts      │                            │
│  │  • Live orderbook panel             │                            │
│  │  • Decision log                     │                            │
│  └──────────────┬──────────────────────┘                            │
│                 │ REST + WebSocket                                   │
│  ┌──────────────▼──────────────────────┐                            │
│  │  FastAPI (Python asyncio)           │                            │
│  │  ┌──────────────────────────────┐   │                            │
│  │  │ KalshiSigner (RSA-PSS/SHA256)│   │  ← No SDK, native signing  │
│  │  │ AlphaEngine (Four Factors)   │   │  ← BALLDONTLIE GOAT tier   │
│  │  │ KellySizer (0.25x Kelly)     │   │  ← 3% max per contract     │
│  │  │ SentimentGuardrail (Sonar)   │   │  ← Toggle, abort < -0.4    │
│  │  │ OrderbookManager (WS delta)  │   │  ← Real-time local book    │
│  │  │ ReconciliationManager (60s)  │   │  ← Halt at 0.1% discrep.   │
│  │  │ LedgerEngine (double-entry)  │   │  ← PostgreSQL journal      │
│  │  └──────────────────────────────┘   │                            │
│  └──────────────┬──────────────────────┘                            │
│                 │ asyncpg                                            │
│  ┌──────────────▼──────────────────────┐                            │
│  │  PostgreSQL 16                      │  Double-entry ledger       │
│  │  • journal_entries                  │  journal_lines             │
│  │  • reconciliation_log               │  accounts                  │
│  └─────────────────────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. RSA-PSS Signing (`apollo/signer.py`)

Kalshi requires every authenticated request to include a signature constructed as:

```
message  = timestamp_ms + METHOD + /path/without/query/params
signature = RSA-PSS( SHA256, message, salt_length=32 )
header   = Base64(signature)
```

The `KalshiSigner` class implements this natively using `cryptography` — no third-party Kalshi SDK is used. The signature is included in three HTTP headers:

```
KALSHI-ACCESS-KEY: <your-key-id>
KALSHI-ACCESS-SIGNATURE: <base64-signature>
KALSHI-ACCESS-TIMESTAMP: <epoch-ms>
```

### 2. Four Factors Alpha Engine (`apollo/alpha_engine.py`)

Win probability is modeled with Dean Oliver's Four Factors:

| Factor | Weight | Description |
|--------|--------|-------------|
| eFG%   | 0.40   | Effective FG% = (FGM + 0.5×3PM) / FGA |
| TO%    | 0.25   | Turnover rate (lower = better) |
| REB    | 0.20   | Rebounding rate |
| FTR    | 0.15   | Free throw rate |

**Critical alpha adjustment:** `+1 rebound/game = +2.62% win probability`

The composite score is converted to head-to-head win probability and compared against Kalshi's market price. If `P_market > P_true + 0.05` (the 5% retail hype premium), a **NO-side signal** is generated.

### 3. Quarter-Kelly Position Sizing (`apollo/kelly.py`)

```
K* = ( p*(b+1) - 1 ) / b      # Full Kelly formula
K_quarter = 0.25 × K*          # Quarter-Kelly for stability
K_capped = min(K_quarter, 3%)  # Hard cap per contract
```

Where `p` = model win probability and `b` = net payout ratio from Kalshi's market price.

### 4. Sentiment Guardrail (`apollo/sentiment.py`)

When enabled (Perplexity API key provided):
1. Queries Perplexity Sonar for last 24h news on the matchup
2. Extracts a sentiment score in `[-1.0, +1.0]`
3. If `score < -0.4` → **aborts the trade** (prevents stale-data value traps)

### 5. Double-Entry Ledger (`apollo/reconciliation.py`)

Every fill creates atomic journal entries:
```
Debit  Assets:Position   +$amount
Credit Assets:Cash        -$amount
```

Every 60 seconds, `ReconciliationManager` compares internal ledger cash against `GET /portfolio/balance`. If `|discrepancy| / balance > 0.1%`:
- Sets `trading_halted = True` (all order submissions check this flag)
- Exports `Audit_Failure_<timestamp>.csv` with last 1000 journal lines
- Logs to `reconciliation_log` table

---

## Project Structure

```
apollo-agent/
├── backend/
│   ├── apollo/
│   │   ├── __init__.py
│   │   ├── signer.py           KalshiSigner — RSA-PSS native signing
│   │   ├── kelly.py            KellySizer — Quarter-Kelly + 3% cap
│   │   ├── alpha_engine.py     AlphaEngine — Four Factors + BALLDONTLIE
│   │   ├── sentiment.py        SentimentGuardrail — Perplexity Sonar
│   │   ├── orderbook.py        OrderbookManager — WS delta channel
│   │   ├── kalshi_client.py    KalshiClient — REST API wrapper
│   │   ├── reconciliation.py   LedgerEngine + ReconciliationManager
│   │   └── trade_engine.py     TradeEngine — full pipeline orchestrator
│   ├── main.py                 FastAPI server
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        Redirect logic
│   │   │   ├── onboarding/     Secure key onboarding UI
│   │   │   └── dashboard/      Bloomberg-style trading dashboard
│   │   ├── components/
│   │   │   ├── charts/         PnLChart + DivergenceChart (ApexCharts)
│   │   │   └── dashboard/      OrderbookPanel + DecisionLog
│   │   └── lib/
│   │       ├── store.ts        Zustand session store
│   │       └── api.ts          Type-safe API client
│   ├── next.config.ts
│   ├── package.json
│   └── Dockerfile
├── infra/
│   └── railway-template.md     Per-instance deployment guide
├── docker-compose.yml          Local dev (all 3 services)
├── railway.json                Railway deployment config
├── .env.example
├── .gitignore
└── README.md
```

---

## Local Development

### Prerequisites
- Docker + Docker Compose
- Node 20+ (for local frontend dev without Docker)
- Python 3.12+ (for local backend dev without Docker)

### Quick Start (Docker)

```bash
git clone <your-repo>
cd apollo-agent
cp .env.example .env

docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs

### Backend Only (local Python)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Requires Postgres running — update DATABASE_URL in .env
uvicorn main:app --reload --port 8000
```

### Frontend Only (local Node)

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

---

## Railway Deployment

See `infra/railway-template.md` for the full guide.

**TL;DR — each tester gets their own isolated instance:**

1. Fork the repo
2. New Railway project → Deploy from GitHub repo
3. Add PostgreSQL plugin
4. Set `DATABASE_URL` (reference plugin variable)
5. Set frontend `NEXT_PUBLIC_API_URL` to backend Railway URL
6. Each instance has dedicated DB, dedicated URL, isolated keys

---

## Using the Dashboard

1. **Navigate to `/onboarding`**
2. Enter:
   - **Kalshi Access Key ID** (UUID from your Kalshi account)
   - **Private Key** — upload your `.key` file or paste PEM contents
   - **BALLDONTLIE API Key** — GOAT tier required for player/team stats + brackets
   - **Perplexity API Key** — optional, enables sentiment guardrail
   - **Bankroll** — your starting capital (max trade = 3% of this)
   - **Mode** — SIM (paper trade) or LIVE (real orders)
3. Click **LAUNCH APOLLO-AGENT**

**On the Dashboard:**
- Enter a matchup (team names, BALLDONTLIE IDs, Kalshi ticker, market YES price)
- Click **ANALYZE** to get the alpha signal without trading
- Click **SIM/LIVE TRADE** to execute the full pipeline

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session` | Create session with credentials |
| GET | `/api/session/{id}` | Session status + halt status |
| GET | `/api/markets/{id}` | Open Kalshi NCAAB markets |
| GET | `/api/orderbook/{id}/{ticker}` | Local orderbook snapshot |
| POST | `/api/analyze` | Run alpha analysis (no trade) |
| POST | `/api/trade` | Full pipeline + order execution |
| GET | `/api/portfolio/{id}` | Kalshi balance + positions |
| GET | `/api/ledger/balance/{id}` | Internal ledger cash balance |
| GET | `/api/reconciliation/{id}` | Last recon result |
| GET | `/api/decisions/{id}` | Recent trade decision log |
| WS | `/ws/{id}` | Real-time orderbook push events |

---

## Risk Controls Summary

| Control | Value | Implementation |
|---------|-------|----------------|
| Kelly fraction | 0.25× (Quarter-Kelly) | `KellySizer` |
| Max per contract | 3% of bankroll | `KellySizer._MAX_POSITION_PCT` |
| Min edge required | 2% | `KellySizer.MIN_EDGE` |
| Sentiment abort | score < -0.4 | `SentimentGuardrail` |
| Recon halt | discrepancy > 0.1% | `ReconciliationManager` |
| Recon interval | every 60 seconds | `ReconciliationManager` |
| Hype threshold | P_market > P_true + 5% | `AlphaEngine.HYPE_THRESHOLD` |

---

## BALLDONTLIE API Tiers

| Tier | Required For |
|------|-------------|
| Free | Team directory |
| All-Star | Live game scores |
| **GOAT** | **Player/team stats, brackets, betting odds** (required) |

GOAT tier required for the Four Factors model and tournament path analysis.

---

## Disclaimer

Apollo-Agent is an experimental research system. Prediction market trading involves real financial risk. Always start in **SIM mode** to validate signal quality before going live. The NO-side 74% win rate and rebound alpha are historical research findings — past performance does not guarantee future results.
