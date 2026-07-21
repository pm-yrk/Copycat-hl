
# Copycat

**Live Hyperliquid wallet intelligence and a consensus-weighted market index.**

Copycat is a data product that discovers active Hyperliquid wallets, evaluates
their trading history, selects a high-quality live cohort and turns their
current positioning into transparent market signals.

> Status: active personal project and portfolio case study.

## Overview

The project answers a practical question:

> What are consistently profitable Hyperliquid wallets doing right now, and
> where do they genuinely agree?

Copycat combines wallet discovery, historical scoring, live position
monitoring, market aggregation and public JSON snapshots in one system.

## Key features

- Discovers wallets from live Hyperliquid market activity.
- Deeply analyses wallet fills, fees, funding and trading consistency.
- Selects a live cohort using strict minimum-history and quality rules.
- Aggregates long and short exposure by asset.
- Produces an equity-normalised consensus portfolio.
- Lets opposing long and short positions cancel rather than overstating a
  divided signal.
- Excludes stablecoins from directional portfolio allocation.
- Publishes read-only dashboard and API snapshots to Cloudflare R2.
- Includes market narrative, catalyst monitoring and data-quality checks.
- Supports desktop and mobile dashboards.

## Architecture

```text
Hyperliquid public APIs
        |
        v
Wallet discovery and registry
        |
        v
Historical quality analysis
        |
        v
Qualified live wallet cohort
        |
        v
Local snapshot publisher
        |
        +--> Consensus index
        +--> Asset signals
        +--> Exposure and flow tables
        +--> Data-quality snapshots
        |
        v
Cloudflare R2 JSON snapshots
        |
        v
Next.js dashboard and public data pages
```

## Repository structure

```text
frontend/   Next.js dashboard and public data interface
backend/    Application and API services
scripts/    Discovery, ranking, publishing and maintenance tools
docs/       Methodology, architecture and implementation notes
infra/      Infrastructure configuration
supabase/   Earlier database integration assets
```

## Consensus portfolio methodology

Each selected wallet is treated as a source of information rather than being
weighted only by account size.

For each wallet:

1. Position value is divided by the wallet's perpetual-account equity.
2. The wallet's total signal contribution is capped.
3. Higher-ranked wallets receive a small additional influence.
4. Long and short positions in the same asset cancel.
5. Assets require participation from multiple wallets and a minimum level of
   agreement.
6. Stablecoins are excluded from directional allocations.
7. Remaining asset scores are normalised into portfolio weights.

If every selected wallet is only long BTC, the portfolio can be 100% BTC. A
51% long versus 49% short split produces little or no portfolio allocation.

The published index is synthetic. It measures how the consensus portfolio
would move from its start point; it is not a claim of the wallets' realised
historical profit.

## Technology

- Python
- TypeScript
- Next.js
- React
- Hyperliquid public APIs
- SQLite
- Cloudflare R2
- PowerShell automation
- Git and GitHub

## Running locally

### Requirements

- Python 3
- Node.js and npm
- A copy of the required environment example files
- Hyperliquid public API access
- Cloudflare R2 credentials only when publishing snapshots

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Configuration

Copy the relevant `.env.example` file to its local non-example filename and
replace placeholder values. Never commit real credentials.

The snapshot publisher has its own example configuration at:

```text
scripts/local_snapshot_publisher/publisher.env.example
```

## Data quality and limitations

- Copycat uses public Hyperliquid data and is subject to API availability,
  caching and history limits.
- A wallet may be excluded when its complete history cannot be verified.
- The live cohort is selected from the locally indexed universe; it is not a
  guaranteed platform-wide ranking.
- Wallet values can differ between explorers when perp equity, spot balances
  and unified-account collateral are labelled differently.
- The index is informational and does not include execution costs, slippage or
  guaranteed tradability.
- Nothing in this repository is financial advice.

## Portfolio case study

A more interview-focused explanation is available in
[`docs/PORTFOLIO_CASE_STUDY.md`](docs/PORTFOLIO_CASE_STUDY.md).

## Security

Never commit passwords, API secrets, private keys, bot tokens, wallet private
keys, local databases or runtime output. See [`SECURITY.md`](SECURITY.md).

## Ownership

Copyright (c) 2026 Paul Murrin. All rights reserved.

No open-source licence is granted unless a separate `LICENSE` file is added.
