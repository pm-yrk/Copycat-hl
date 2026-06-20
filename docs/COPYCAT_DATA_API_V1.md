# Copycat Data API v1

Copycat Data API is the start of Copycat's own Hyperliquid intelligence layer.
It reduces Nansen to an optional fallback and turns Copycat's stored wallet data
into a product that can later be sold as an API.

## What v1 includes

- API page at `/api-access`.
- Public API status endpoint.
- API-key protected leaderboard, wallet profile, fills, exposure, and live-events endpoints.
- API key storage with hashed keys only.
- API usage logging and basic per-key minute rate limits.
- Hyperliquid WebSocket worker for tracked-wallet live fill events.
- Historical source registry focused on official/public Hyperliquid sources.

## Endpoints

Public:

- `GET /api/data/v1/status`
- `GET /api/data/v1/historical-sources`

API-key protected:

- `GET /api/data/v1/leaderboard`
- `GET /api/data/v1/wallet/{wallet}`
- `GET /api/data/v1/wallet/{wallet}/fills`
- `GET /api/data/v1/exposures`
- `GET /api/data/v1/recent-events`

Authenticated app users:

- `POST /api/data/v1/keys?label=My%20Key`

The plain API key is returned once only. The database stores a salted hash.

## Live dashboard speed

The `hwt-live-events` worker subscribes to Hyperliquid `userFills` streams for
active Copycat wallets. When a tracked wallet gets filled, Copycat stores the
fill in `copycat_live_events`. `/api/recent-orders` now prefers these live events
when present, so the dashboard can update much faster than waiting for the full
50-wallet position-diff collector cycle.

This is fill/event speed, not guaranteed visibility for every unfilled limit
order. Hyperliquid exposes `orderUpdates`, but v1 keeps that disabled by default
until we validate public message attribution in production.

## Historical data plan

Best legal/independent sources:

1. Hyperliquid official Info API
   - user state, portfolio, user fills by time, funding, ledger updates.
   - We must store results ourselves permanently.

2. Hyperliquid official WebSocket
   - real-time tracked-wallet fills and account/order streams.
   - Complete from the moment Copycat subscribes.

3. Hyperliquid official archive bucket
   - official historical market data such as L2 snapshots and asset contexts.
   - Official docs say archive data may be delayed or missing and does not cover every dataset.

Important: this makes Copycat independent going forward. It cannot magically
create a fully-owned one-year wallet universe from before Copycat started
collecting. A one-off third-party backfill can still be used, but should be
labelled separately from Copycat-owned data.
