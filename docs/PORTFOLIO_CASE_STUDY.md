
# Copycat portfolio case study

## The problem

Public blockchain data is abundant, but raw wallet activity is difficult to
turn into a useful decision-support product. A large account is not
automatically skilled, recent profit may be luck, and simple position totals
can be dominated by whales or contradictory long and short exposure.

Copycat was designed to turn that noisy data into a clearer analytical system.

## My role

I defined the product, data-quality rules, dashboard requirements and
operational workflow. I used AI-assisted development while reviewing outputs,
testing calculations, inspecting live data and refining the system when
results did not match the intended business meaning.

This project demonstrates:

- analytical problem definition;
- data validation;
- KPI and scoring design;
- dashboard product design;
- API and data-pipeline thinking;
- automation and operational monitoring;
- iterative testing and debugging;
- explaining technical results in business language.

## Key analytical decisions

### 1. Separate account size from skill

Wallet selection uses trading history, profitability, consistency and sample
quality rather than treating the largest accounts as the best traders.

### 2. Require sufficient evidence

Wallets need minimum history, activity and profitable periods before they can
qualify for the strict cohort.

### 3. Normalise wallet positions

Position values are compared with each wallet's own perp equity. This prevents
one large wallet from automatically controlling the portfolio.

### 4. Cancel disagreement

Long and short positions in the same asset offset one another. A closely split
market should not appear as a high-conviction signal.

### 5. Exclude stablecoins from directional allocation

Stablecoins are collateral or inactive capital. They are not treated as a
bullish market position.

### 6. Preserve transparent limitations

The product distinguishes between:

- total wallet value;
- perp equity;
- open perp exposure;
- raw dollar positioning;
- consensus-weighted portfolio allocation.

## Data flow

```text
Live trades
  -> wallet discovery
  -> local registry
  -> historical analysis
  -> strict qualification
  -> selected live cohort
  -> live states and fills
  -> aggregate signals and index
  -> R2 snapshots
  -> dashboard/API
```

## Reliability controls

- Cached last-good wallet states during temporary API failures.
- Explicit live, stale, partial and missing data states.
- Public snapshot verification after publisher changes.
- Safe-hold behaviour when fewer than 50 wallets satisfy strict rules.
- Automated backups and rollback for production patches.
- Read-only audits before changing calculations.

## Examples of problems solved

- Identified when an API page requested 30 wallets but displayed only 24.
- Distinguished total wallet value from perp equity to reconcile explorer
  differences.
- Removed an indirect token-pricing method that could inflate wallet values.
- Aligned dashboard totals and API totals to the same 50-wallet source.
- Reworked portfolio allocation so opposing positions cancel.
- Moved index state to persistent storage so publisher updates do not restart
  historical performance.

## Honest limitations

The system is not a historical investment backtest and does not guarantee
outperformance. Hyperliquid's public history limits can prevent complete
analysis of some wallets. The selected cohort is the best qualified group from
the locally indexed universe, not a guaranteed ranking of every account on the
platform.

## Interview summary

> I built a live crypto analytics product that discovers wallets, scores their
> historical quality, selects a qualified cohort and converts their positions
> into a consensus-weighted index. The most important work was not just the
> dashboard: it was defining reliable metrics, reconciling conflicting data
> sources, automating the pipeline and making limitations explicit.
