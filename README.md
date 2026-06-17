# Hyper Wallet Tracker SaaS v1

A production-oriented SaaS scaffold for selling the Hyperliquid smart-wallet dashboard as a subscription product.

This package turns the local prototype into a hosted product shape:

- FastAPI backend
- Postgres database schema
- scheduled collector job every 15 minutes
- automatic daily wallet refresh at midnight
- Next.js customer dashboard
- Supabase login integration
- Stripe subscription gating
- Telegram group alerts
- Render deployment templates

## What this is

This is a deployable SaaS starter kit. It is not live until you create and connect the required external accounts:

- Supabase project
- Postgres database
- Stripe account/products
- Telegram bot/group
- hosting account, for example Render
- Nansen API key

## Important commercial note

Before selling publicly, get legal/compliance advice and check your data-provider rights. In particular, if using Nansen-derived candidate discovery, confirm your license permits commercial use in the way you intend.

Position the product as market intelligence / wallet-flow analytics, not financial advice.

## Structure

```text
backend/              FastAPI API + worker jobs
frontend/             Next.js dashboard/login/pricing UI
supabase/schema.sql   database schema
infra/render.yaml     Render deployment blueprint template
docs/                 deployment, operations, alerts, compliance notes
```

## Production behavior

```text
Every 15 minutes:
  collect latest qualified-wallet positions
  recompute signals and portfolio targets
  check dump/accumulation alert rules
  post Telegram alerts if triggered

Every midnight:
  pull fresh Nansen candidates
  score wallets using the quality model
  refresh top qualified wallets
  collect fresh positions
  compute signals
  post Telegram admin summary
```

## Quick local test

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
python -m app.jobs.init_db
python -m app.jobs.collect_once
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

## Deployment order

1. Create Supabase project and run `supabase/schema.sql`.
2. Create Stripe product, prices, webhook secret.
3. Create Telegram bot and group/channel.
4. Set environment variables in your host.
5. Deploy backend API.
6. Deploy collector cron job every 15 minutes.
7. Deploy daily-refresh cron job at midnight.
8. Deploy frontend.
9. Send yourself a Telegram test message.
10. Run the daily-refresh job once manually.

See `docs/DEPLOYMENT.md`.
