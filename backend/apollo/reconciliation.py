"""
ReconciliationService — Double-entry ledger + live balance reconciliation.

Architecture
------------
Every fill event creates ATOMIC journal entries:
    Debit  Assets:Position   +amount
    Credit Assets:Cash        -amount

Every 60 seconds, the ReconciliationManager compares the internal ledger
against Kalshi's /portfolio/balance endpoint.

If discrepancy > 0.1% of total balance → HALT trading + export Audit_Failure.csv
"""

import asyncio
import csv
import io
import logging
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

import asyncpg
import httpx

from .signer import KalshiSigner

log = logging.getLogger("apollo.reconciliation")

# Halt threshold: 0.1% discrepancy
HALT_THRESHOLD_PCT = Decimal("0.001")
RECONCILE_INTERVAL_SECONDS = 60
KALSHI_BASE_URL = "https://trading-api.kalshi.com"


# ──────────────────────────────────────────────────────────────────────────────
# Enums & Models
# ──────────────────────────────────────────────────────────────────────────────

class AccountType(str, Enum):
    ASSETS_CASH = "Assets:Cash"
    ASSETS_POSITION = "Assets:Position"
    LIABILITIES_OPEN_ORDER = "Liabilities:OpenOrder"
    EQUITY_PNL = "Equity:PnL"
    INCOME_REALIZED = "Income:Realized"
    EXPENSE_FEES = "Expense:Fees"


class ReconciliationStatus(str, Enum):
    OK = "OK"
    HALTED = "HALTED"
    PENDING = "PENDING"


# ──────────────────────────────────────────────────────────────────────────────
# Database schema helpers
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id              BIGSERIAL PRIMARY KEY,
    entry_id        UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    description     TEXT,
    fill_id         TEXT,           -- Kalshi fill/order ID
    is_reconciled   BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS journal_lines (
    id              BIGSERIAL PRIMARY KEY,
    entry_id        UUID NOT NULL REFERENCES journal_entries(entry_id),
    account_name    TEXT NOT NULL REFERENCES accounts(name),
    debit_cents     BIGINT NOT NULL DEFAULT 0,  -- positive = debit
    credit_cents    BIGINT NOT NULL DEFAULT 0,  -- positive = credit
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reconciliation_log (
    id              BIGSERIAL PRIMARY KEY,
    checked_at      TIMESTAMPTZ DEFAULT NOW(),
    ledger_balance_cents    BIGINT NOT NULL,
    kalshi_balance_cents    BIGINT NOT NULL,
    discrepancy_cents       BIGINT NOT NULL,
    discrepancy_pct         NUMERIC(10,6) NOT NULL,
    status                  TEXT NOT NULL,       -- OK | HALTED
    audit_file              TEXT                 -- path if halted
);

-- Seed core accounts (idempotent)
INSERT INTO accounts (name, type) VALUES
    ('Assets:Cash',              'asset'),
    ('Assets:Position',          'asset'),
    ('Liabilities:OpenOrder',    'liability'),
    ('Equity:PnL',               'equity'),
    ('Income:Realized',          'income'),
    ('Expense:Fees',             'expense')
ON CONFLICT (name) DO NOTHING;
"""


# ──────────────────────────────────────────────────────────────────────────────
# Ledger Engine
# ──────────────────────────────────────────────────────────────────────────────

class LedgerEngine:
    """
    Records every fill event as atomic double-entry journal entries.
    All amounts are stored in integer CENTS to avoid floating-point drift.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def initialize(self) -> None:
        """Run schema migrations."""
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            # Idempotent migration: add UNIQUE constraint on entry_id if missing
            # (needed for journal_lines FK reference to work)
            await conn.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conrelid = 'journal_entries'::regclass
                          AND contype = 'u'
                          AND conname = 'journal_entries_entry_id_key'
                    ) THEN
                        ALTER TABLE journal_entries ADD CONSTRAINT journal_entries_entry_id_key UNIQUE (entry_id);
                    END IF;
                END$$;
            """)

    async def record_fill(
        self,
        fill_id: str,
        amount_cents: int,
        description: str = "",
        fee_cents: int = 0,
    ) -> str:
        """
        Record a contract fill:
            Debit  Assets:Position   +amount_cents
            Credit Assets:Cash        -amount_cents
            Debit  Expense:Fees       +fee_cents  (if applicable)
            Credit Assets:Cash        -fee_cents  (if applicable)

        Returns the UUID of the journal entry.
        """
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                entry_id = await conn.fetchval(
                    """
                    INSERT INTO journal_entries (description, fill_id)
                    VALUES ($1, $2)
                    RETURNING entry_id::text
                    """,
                    description or f"Fill {fill_id}",
                    fill_id,
                )
                # Position debit / Cash credit
                await conn.executemany(
                    """
                    INSERT INTO journal_lines (entry_id, account_name, debit_cents, credit_cents)
                    VALUES ($1, $2, $3, $4)
                    """,
                    [
                        (entry_id, AccountType.ASSETS_POSITION, amount_cents, 0),
                        (entry_id, AccountType.ASSETS_CASH, 0, amount_cents),
                    ],
                )
                # Fees (optional)
                if fee_cents > 0:
                    fee_entry = await conn.fetchval(
                        """
                        INSERT INTO journal_entries (description, fill_id)
                        VALUES ($1, $2)
                        RETURNING entry_id::text
                        """,
                        f"Fee for fill {fill_id}",
                        fill_id,
                    )
                    await conn.executemany(
                        """
                        INSERT INTO journal_lines (entry_id, account_name, debit_cents, credit_cents)
                        VALUES ($1, $2, $3, $4)
                        """,
                        [
                            (fee_entry, AccountType.EXPENSE_FEES, fee_cents, 0),
                            (fee_entry, AccountType.ASSETS_CASH, 0, fee_cents),
                        ],
                    )
        return entry_id

    async def record_settlement(
        self,
        fill_id: str,
        position_cents: int,
        payout_cents: int,
    ) -> str:
        """
        On contract settlement:
            Debit  Assets:Cash          +payout_cents
            Credit Assets:Position       -position_cents
            Credit/Debit Income:Realized  ±(payout - position)
        """
        pnl_cents = payout_cents - position_cents
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                entry_id = await conn.fetchval(
                    """
                    INSERT INTO journal_entries (description, fill_id)
                    VALUES ($1, $2)
                    RETURNING entry_id::text
                    """,
                    f"Settlement {fill_id}",
                    fill_id,
                )
                lines = [
                    (entry_id, AccountType.ASSETS_CASH, payout_cents, 0),
                    (entry_id, AccountType.ASSETS_POSITION, 0, position_cents),
                ]
                if pnl_cents >= 0:
                    lines.append((entry_id, AccountType.INCOME_REALIZED, 0, pnl_cents))
                else:
                    lines.append((entry_id, AccountType.EQUITY_PNL, abs(pnl_cents), 0))
                await conn.executemany(
                    """
                    INSERT INTO journal_lines (entry_id, account_name, debit_cents, credit_cents)
                    VALUES ($1, $2, $3, $4)
                    """,
                    lines,
                )
        return entry_id

    async def get_cash_balance_cents(self) -> int:
        """Return current Assets:Cash balance from the ledger."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(credit_cents), 0) - COALESCE(SUM(debit_cents), 0) AS balance
                FROM journal_lines
                WHERE account_name = $1
                """,
                AccountType.ASSETS_CASH,
            )
            return int(row["balance"])

    async def verify_double_entry(self) -> bool:
        """Assert Σ debits == Σ credits across all lines (accounting identity)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT SUM(debit_cents) AS d, SUM(credit_cents) AS c FROM journal_lines"
            )
            return row["d"] == row["c"]


# ──────────────────────────────────────────────────────────────────────────────
# Reconciliation Manager
# ──────────────────────────────────────────────────────────────────────────────

class ReconciliationManager:
    """
    Runs every 60 seconds.  Compares internal ledger cash balance against
    Kalshi's /portfolio/balance endpoint.

    If |discrepancy| / kalshi_balance > 0.1%:
        1. Set trading_halted = True (all order submission checks this flag)
        2. Export Audit_Failure.csv with the last 1000 journal lines
        3. Log to reconciliation_log table
    """

    def __init__(
        self,
        ledger: LedgerEngine,
        signer: KalshiSigner,
        pool: asyncpg.Pool,
        halt_callback=None,
    ):
        self._ledger = ledger
        self._signer = signer
        self._pool = pool
        self._halt_callback = halt_callback  # async callable(reason: str)
        self.trading_halted: bool = False
        self.status: ReconciliationStatus = ReconciliationStatus.PENDING
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run_loop(self) -> None:
        while True:
            try:
                await self._reconcile_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("Reconciliation error: %s", exc, exc_info=True)
            await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)

    async def _reconcile_once(self) -> None:
        ledger_cents = await self._ledger.get_cash_balance_cents()
        kalshi_cents = await self._fetch_kalshi_balance_cents()

        if kalshi_cents == 0:
            log.warning("Kalshi balance returned 0 — skipping reconciliation tick")
            return

        discrepancy = abs(ledger_cents - kalshi_cents)
        discrepancy_pct = Decimal(str(discrepancy)) / Decimal(str(kalshi_cents))

        log.info(
            "Reconciliation: ledger=%d¢ kalshi=%d¢ diff=%d¢ (%.4f%%)",
            ledger_cents, kalshi_cents, discrepancy, float(discrepancy_pct) * 100,
        )

        if discrepancy_pct > HALT_THRESHOLD_PCT:
            await self._halt_and_export(ledger_cents, kalshi_cents, discrepancy, discrepancy_pct)
        else:
            self.status = ReconciliationStatus.OK
            await self._log_reconciliation(
                ledger_cents, kalshi_cents, discrepancy, discrepancy_pct, "OK", None
            )

    async def _fetch_kalshi_balance_cents(self) -> int:
        path = "/trade-api/v2/portfolio/balance"
        headers = self._signer.build_auth_headers("GET", path)
        async with httpx.AsyncClient(base_url=KALSHI_BASE_URL, timeout=10) as client:
            resp = await client.get(path, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            # Kalshi returns balance in cents
            return int(data.get("balance", 0))

    async def _halt_and_export(
        self,
        ledger_cents: int,
        kalshi_cents: int,
        discrepancy: int,
        discrepancy_pct: Decimal,
    ) -> None:
        self.trading_halted = True
        self.status = ReconciliationStatus.HALTED
        log.critical(
            "TRADING HALTED — reconciliation discrepancy %.4f%% exceeds 0.1%% threshold",
            float(discrepancy_pct) * 100,
        )

        csv_path = f"/tmp/Audit_Failure_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        await self._export_audit_csv(csv_path)

        await self._log_reconciliation(
            ledger_cents, kalshi_cents, discrepancy, discrepancy_pct, "HALTED", csv_path
        )

        if self._halt_callback:
            await self._halt_callback(
                f"Discrepancy {float(discrepancy_pct)*100:.4f}% — audit at {csv_path}"
            )

    async def _export_audit_csv(self, path: str) -> None:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    je.entry_id,
                    je.created_at,
                    je.description,
                    je.fill_id,
                    jl.account_name,
                    jl.debit_cents,
                    jl.credit_cents
                FROM journal_lines jl
                JOIN journal_entries je ON je.entry_id = jl.entry_id
                ORDER BY jl.id DESC
                LIMIT 1000
                """
            )
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["entry_id", "created_at", "description", "fill_id",
                            "account_name", "debit_cents", "credit_cents"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(row))
        log.info("Audit CSV exported to %s (%d rows)", path, len(rows))

    async def _log_reconciliation(
        self, ledger, kalshi, discrepancy, discrepancy_pct, status, audit_file
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO reconciliation_log
                    (ledger_balance_cents, kalshi_balance_cents, discrepancy_cents,
                     discrepancy_pct, status, audit_file)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                ledger, kalshi, discrepancy, float(discrepancy_pct), status, audit_file,
            )
