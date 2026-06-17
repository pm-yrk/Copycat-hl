# Deployment guide

## 1. Supabase

Create a Supabase project, then run `supabase/schema.sql` in the SQL editor.

Copy these values:

- Project URL -> `NEXT_PUBLIC_SUPABASE_URL`
- Anon public key -> `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- JWT secret -> `SUPABASE_JWT_SECRET`
- Postgres connection string -> `DATABASE_URL`

## 2. Stripe

Create a monthly product price and annual product price.

Set:

- `STRIPE_SECRET_KEY`
- `STRIPE_PRICE_ID_MONTHLY`
- `STRIPE_PRICE_ID_ANNUAL`
- `STRIPE_WEBHOOK_SECRET`

Webhook endpoint:

```text
https://YOUR_API_DOMAIN/api/stripe/webhook
```

Enable events:

```text
checkout.session.completed
customer.subscription.updated
customer.subscription.deleted
```

## 3. Telegram

Create a bot using BotFather. Add the bot to your group/channel and give it permission to post.

Set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Test:

```bash
cd backend
python -m app.jobs.test_telegram
```

## 4. Hosting

Use `infra/render.yaml` as the starting blueprint:

- `hwt-api` web service
- `hwt-frontend` web service
- `hwt-collector-15m` cron job
- `hwt-daily-refresh-midnight` cron job

After deployment, manually run:

```bash
python -m app.jobs.init_db
python -m app.jobs.daily_refresh
```

Then open the frontend dashboard.

## 5. Production checklist

- Use real HTTPS domains.
- Set `ALLOW_DEMO_AUTH=false`.
- Do not expose secrets in frontend env variables.
- Set Stripe webhook secret.
- Confirm Supabase JWT verification works.
- Confirm daily refresh has run successfully.
- Confirm Telegram alert test works.
- Confirm alerts are not too noisy before opening to customers.
